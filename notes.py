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

import json
import re
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

            conn.commit()

        embedding = embed_and_store(note_id, saved_content)
        run_integration(note_id, saved_content, embedding)

        return redirect(url_for("notes.index"))

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

        conn.commit()

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
        conn.commit()
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


@notes_bp.route("/graph")
@require_login
def graph_view():
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            # 1. Fetch approved notes (FIXED: Added 'content' column)
            cur.execute("""
                SELECT id, note_type, content FROM notes 
                WHERE status IN ('approved', 'approved_merged')
            """)
            notes = cur.fetchall()
            
            # 2. Fetch topics
            cur.execute("SELECT id, name FROM topics")
            topics = cur.fetchall()
            
            # 3. Fetch links and calculate "Hubs" (nodes with 3+ incoming links)
            cur.execute("""
                SELECT note_id, related_note_id, link_type FROM note_links
            """)
            links = cur.fetchall()
            
            cur.execute("""
                SELECT related_note_id, COUNT(*) as link_count 
                FROM note_links GROUP BY related_note_id HAVING COUNT(*) >= 3
            """)
            hub_notes = {str(row[0]): row[1] for row in cur.fetchall()}

            # 4. Fetch note-to-topic links
            cur.execute("SELECT note_id, topic_id FROM note_topics")
            topic_links = cur.fetchall()

    # Format data for Vis.js
    nodes = []
    # Add Topic Nodes (Hubs)
    for topic_id, name in topics:
        nodes.append({
            "id": f"topic_{topic_id}", "label": name, "shape": "box", 
            "color": {
                "background": "#238636", "border": "#2ea043",
                "hover": {"background": "#238636", "border": "#ffffff"},
                "highlight": {"background": "#238636", "border": "#ffffff"}
            },
            "font": {"color": "#ffffff"}, "size": 20
        })
    
    # Add Note Nodes
    for note_id, note_type, content in notes:
        # Determine the base color
        base_color = "#58a6ff" if note_type == "claim" else "#d29922" if note_type == "reflection" else "#a371f7"
        size = 25 if str(note_id) in hub_notes else 10 
        
        # --- TACTICAL TRUNCATION ---
        # 1. Flatten all newlines/tabs into single spaces
        clean_text = re.sub(r'\s+', ' ', content).strip()
        
        # 2. Cut at a clean word boundary around 90 characters
        limit = 150
        if len(clean_text) > limit:
            truncated = clean_text[:limit]
            last_space = truncated.rfind(' ')
            # Cut at the last space to avoid breaking words
            clean_snippet = truncated[:last_space] + "..." if last_space > 0 else truncated + "..."
        else:
            clean_snippet = clean_text
        # ---------------------------

        nodes.append({
            "id": str(note_id), 
            "label": "", # Keep this empty to hide the text
            "group": note_type.capitalize(), # <-- ADD THIS: Hidden ID for filtering (e.g., 'Claim')
            "title": clean_snippet, 
            "shape": "dot", 
            "color": {
                "background": base_color, "border": base_color,
                "hover": {"background": base_color, "border": "#ffffff"},
                "highlight": {"background": base_color, "border": "#ffffff"}
            },
            "size": size
        })

    edges = []
    # Add Note-to-Note Links (Color-coded by type)
    for source, target, link_type in links:
        edge_color = "#3fb950" if link_type == "supports" else \
                     "#f85149" if link_type == "contradicts" else \
                     "#58a6ff" if link_type == "elaborates" else "#8b949e"
        
        edges.append({
            "from": str(source), "to": str(target), 
            "color": {"color": edge_color, "opacity": 0.6}, 
            "title": link_type.capitalize() # Shows on hover
        })

    # Add Note-to-Topic Links (Dashed lines)
    for note_id, topic_id in topic_links:
        edges.append({
            "from": str(note_id), "to": f"topic_{topic_id}", 
            "color": {"color": "#8b949e", "opacity": 0.3}, "dashes": True
        })

    return render_template("notes/graph.html", 
                           nodes_json=json.dumps(nodes), 
                           edges_json=json.dumps(edges))