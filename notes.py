"""
Notes CRUD -- create, view, delete. Creating a note now goes straight into
review (see new() below) rather than stopping at a separate draft state --
begin_critique_session() is imported from review.py so both paths share the
exact same "create a session, get the critic's first reply" logic.

Every query here goes through get_user_scoped_connection(session["user_id"]),
which is what makes the RLS policies on `notes` (schema.sql) actually
enforce isolation. Notice there's no "WHERE user_id = ..." anywhere in this
file -- that's not an oversight, it's the point. The database enforces it,
so the application code can't forget to.
"""

from classify import classify_note
from db import get_user_scoped_connection
from decorators import require_login
from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from review import begin_critique_session, embed_and_store, run_integration

notes_bp = Blueprint("notes", __name__, url_prefix="/notes")


@notes_bp.route("/")
@require_login
def index():
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, note_type, content, status, created_at "
                "FROM notes ORDER BY created_at DESC"
            )
            notes = cur.fetchall()

    # Pass the raw data to the template. Jinja2 will handle the HTML.
    return render_template("notes/index.html", notes=notes)


@notes_bp.route("/new", methods=["GET", "POST"])
@require_login
def new():
    if request.method == "GET":
        return """
            <p><a href="/notes">&larr; back</a></p>
            <form method="post">
                <textarea name="content" rows="6" cols="50" placeholder="Write your note..."></textarea><br>
                <button type="submit">Submit</button>
            </form>
        """

    content = request.form.get("content", "").strip()
    if not content:
        abort(400)

    # No manual type selection -- classify_note() picks claim/reflection/
    # question automatically, one fast LLM call before anything else happens.
    classify_result = classify_note(content)
    note_type = classify_result["type"]

    if note_type == "question":
        # Open questions skip critique entirely -- interrogating a question
        # about not being answerable enough, before it's even allowed to be
        # saved, is a strange loop that doesn't protect against anything the
        # way it does for a claim (misinformation risk) or a reflection
        # (genuine self-understanding benefit). Auto-approved immediately.
        with get_user_scoped_connection(session["user_id"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO notes (user_id, note_type, content, status, classify_input_tokens, classify_output_tokens)
                    VALUES (%s, %s, %s, 'approved', %s, %s)
                    RETURNING id, content
                    """,
                    (session["user_id"], note_type, content, classify_result["input_tokens"], classify_result["output_tokens"]),
                )
                note_id, saved_content = cur.fetchone()

        embedding = embed_and_store(note_id, saved_content)
        run_integration(note_id, saved_content, embedding)

        return redirect(url_for("notes.view", note_id=note_id))

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notes (user_id, note_type, content, status, classify_input_tokens, classify_output_tokens)
                VALUES (%s, %s, %s, 'under_review', %s, %s)
                RETURNING id
                """,
                (session["user_id"], note_type, content, classify_result["input_tokens"], classify_result["output_tokens"]),
            )
            note_id = cur.fetchone()[0]

    begin_critique_session(note_id, note_type, content)

    return redirect(url_for("review.view", note_id=note_id))


@notes_bp.route("/<uuid:note_id>")
@require_login
def view(note_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, note_type, content, status, created_at FROM notes WHERE id = %s",
                (str(note_id),)
            )
            note = cur.fetchone()
            
    if not note:
        abort(404)
        
    # This route now ONLY returns JSON for the modal
    return jsonify({
        "id": str(note[0]), 
        "type": note[1], 
        "content": note[2], 
        "status": note[3],
        "created_at": note[4].strftime('%Y-%m-%d %H:%M') if note[4] else '',
    })


@notes_bp.route("/<uuid:note_id>/delete", methods=["POST"])
@require_login
def delete(note_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE id = %s", (str(note_id),))
    return redirect(url_for("notes.index"))


@notes_bp.route("/search")
@require_login
def search():
    query = request.args.get("q", "").strip()
    results = []
    
    if query:
        with get_user_scoped_connection(session["user_id"]) as conn:
            with conn.cursor() as cur:
                # Simple search: look for query text in note content
                cur.execute(
                    """
                    SELECT id, note_type, content, status, created_at
                    FROM notes
                    WHERE content ILIKE %s
                    ORDER BY created_at DESC
                    """,
                    (f"%{query}%",)
                )
                results = cur.fetchall()
    
    return render_template("notes/search.html", query=query, results=results)