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

from flask import Blueprint, abort, redirect, request, session, url_for

from classify import classify_note
from decorators import require_login
from db import get_user_scoped_connection
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

    def _note_link(n):
        note_id, note_type, content, status = n[0], n[1], n[2], n[3]
        # under_review has nothing to offer on the detail page except a link
        # forward -- send straight to the live conversation instead.
        href = f"/notes/{note_id}/review" if status == "under_review" else f"/notes/{note_id}"
        return f'<li><a href="{href}">[{note_type}] {content[:60]} -- {status}</a></li>'

    rows = "".join(_note_link(n) for n in notes)
    return f"""
        <p><a href="/">&larr; home</a></p>
        <h2>Your notes</h2>
        <a href="/notes/new">+ New note</a>
        <ul>{rows}</ul>
    """


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
                "SELECT id, note_type, content, status, created_at, merged_into "
                "FROM notes WHERE id = %s",
                (str(note_id),),
            )
            note = cur.fetchone()
            if note is None:
                abort(404)

            # note_links is stored directionally (note_id -> related_note_id)
            # but a link reads both ways -- this note could be either side of
            # the row depending on which one the integration agent treated
            # as the "new" note at the time.
            cur.execute(
                """
                SELECT id, content FROM notes
                WHERE id IN (
                    SELECT related_note_id FROM note_links WHERE note_id = %s
                    UNION
                    SELECT note_id FROM note_links WHERE related_note_id = %s
                )
                """,
                (str(note_id), str(note_id)),
            )
            related = cur.fetchall()

    # If this note belongs to a different user, RLS makes it invisible to
    # this connection -- the query above returns nothing, indistinguishable
    # from a note that doesn't exist at all. No extra ownership check needed.

    # under_review is kept as a fallback for direct URL navigation (e.g. an
    # old link or bookmark) even though index() no longer routes here for
    # it. draft is not handled here at all anymore -- nothing produces that
    # status now, since new() goes straight to under_review.
    if note[3] == "under_review":
        action = f'<a href="/notes/{note[0]}/review">Continue review &rarr;</a>'
    elif note[3] == "merged" and note[5]:
        action = f'<p>Merged into <a href="/notes/{note[5]}">this note</a>.</p>'
    else:
        action = ""  # approved / approved_merged / abandoned -- nothing to do here

    related_html = ""
    if related:
        items = "".join(f'<li><a href="/notes/{r[0]}">{r[1][:60]}</a></li>' for r in related)
        related_html = f"<p>Related notes:</p><ul>{items}</ul>"

    return f"""
        <p><a href="/notes">&larr; back</a></p>
        <p>Type: {note[1]} | Status: {note[3]}</p>
        <p>{note[2]}</p>
        {action}
        {related_html}
        <form method="post" action="/notes/{note[0]}/delete">
            <button type="submit">Delete</button>
        </form>
    """


@notes_bp.route("/<uuid:note_id>/delete", methods=["POST"])
@require_login
def delete(note_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM notes WHERE id = %s", (str(note_id),))
    return redirect(url_for("notes.index"))