"""
Outputs blueprint -- create, view, list, delete generated outputs.

Also handles PDF export via WeasyPrint once that dependency is installed.
Every query goes through get_user_scoped_connection() so RLS enforces
isolation automatically -- no WHERE user_id = ... anywhere in this file.
"""

import html
import json
import os
import re
from db import get_user_scoped_connection
from decorators import require_login
from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from generate import generate_output, SYSTEM_PROMPTS
from io import BytesIO

outputs_bp = Blueprint("outputs", __name__, url_prefix="/outputs")


@outputs_bp.route("/")
@require_login
def index():
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, output_type, topic_query, model_used, created_at "
                "FROM outputs ORDER BY created_at DESC"
            )
            outputs = cur.fetchall()

    return render_template("outputs/index.html", outputs=outputs)


@outputs_bp.route("/new", methods=["GET", "POST"])
@require_login
def new():
    if request.method == "GET":
        return """
            <p><a href="/outputs">&larr; back</a></p>
            <h2>New output</h2>
            <form method="post">
                <label>Topic or question:<br>
                    <textarea name="topic_query" rows="3" cols="60"
                        placeholder="e.g. What have I learned about FATCA compliance?"></textarea>
                </label><br><br>
                <label>Output type:<br>
                    <select name="output_type">
                        <option value="qna">Q&A Document</option>
                        <option value="narration">Narration Script</option>
                        <option value="summary">Topic Summary</option>
                    </select>
                </label><br><br>
                <button type="submit">Generate</button>
            </form>
        """

    topic_query = request.form.get("topic_query", "").strip()
    output_type = request.form.get("output_type", "").strip()

    if not topic_query:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Topic query is required."}), 400
        abort(400, "Topic query is required.")
        
    if output_type not in SYSTEM_PROMPTS:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": f"Invalid output_type: {output_type}"}), 400
        abort(400, f"Invalid output_type: {output_type}")

    try:
        result = generate_output(session["user_id"], topic_query, output_type)
    except ValueError as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": str(e)}), 400
        # Re-render form with error message for traditional submission
        return f"""
            <p><a href="/outputs">&larr; back</a></p>
            <p style="color:red;">{e}</p>
            <form method="post">
                <label>Topic or question:<br>
                    <textarea name="topic_query" rows="3" cols="60">{topic_query}</textarea>
                </label><br><br>
                <label>Output type:<br>
                    <select name="output_type">
                        <option value="qna" {'selected' if output_type == 'qna' else ''}>Q&A Document</option>
                        <option value="narration" {'selected' if output_type == 'narration' else ''}>Narration Script</option>
                        <option value="summary" {'selected' if output_type == 'summary' else ''}>Topic Summary</option>
                    </select>
                </label><br><br>
                <button type="submit">Generate</button>
            </form>
        """

    # If it's an AJAX request from the modal, return JSON instead of redirecting
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"success": True, "output_id": result["id"]})

    # Traditional form submission - redirect
    return redirect(url_for("outputs.view", output_id=result["id"]))


@outputs_bp.route("/<uuid:output_id>")
@require_login
def view(output_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, output_type, topic_query, generated_content, created_at "
                "FROM outputs WHERE id = %s",
                (str(output_id),)
            )
            output = cur.fetchone()
            
    if not output:
        abort(404)
    
    # Process Markdown formatting in the content
    content = output[3]
    safe_content = html.escape(content)
    
    # Convert bold and italics ONLY
    safe_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', safe_content)
    safe_content = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', safe_content)
    
    # Convert bullets to simple bold with indent (no div wrapper)
    safe_content = re.sub(r'^- (.+)$', r'&nbsp;&nbsp;• \1', safe_content, flags=re.MULTILINE)
    
    # Convert headings to bold text (not HTML headings)
    safe_content = re.sub(r'^### (.+)$', r'<strong>\1</strong>', safe_content, flags=re.MULTILINE)
    safe_content = re.sub(r'^## (.+)$', r'<strong>\1</strong>', safe_content, flags=re.MULTILINE)
    safe_content = re.sub(r'^# (.+)$', r'<strong style="font-size: 1.1em;">\1</strong>', safe_content, flags=re.MULTILINE)

    # Convert [Note UUID] to clickable links
    safe_content = re.sub(
        r'\[Note ([0-9a-f-]+)\]',
        r'<a href="#" data-note-link="\1" style="color: var(--primary); font-weight: 600; cursor: pointer;">[View Note]</a>',
        safe_content
    )
    
    # This route now ONLY returns JSON for the modal
    return jsonify({
        "id": str(output[0]), 
        "type": output[1], 
        "topic": output[2],
        "content": safe_content, 
        "created_at": output[4].strftime('%Y-%m-%d %H:%M') if output[4] else '',
        "model": "Haiku" 
    })


@outputs_bp.route("/<uuid:output_id>/regenerate", methods=["POST"])
@require_login
def regenerate(output_id):
    """Re-generate an existing output with the same topic/type, replacing content."""
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT topic_query, output_type FROM outputs WHERE id = %s",
                (str(output_id),),
            )
            existing = cur.fetchone()
            if existing is None:
                abort(404)

    topic_query, output_type = existing

    try:
        result = generate_output(session["user_id"], topic_query, output_type, is_regeneration=True)
    except ValueError as e:
        return redirect(url_for("outputs.index"))

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE outputs
                SET generated_content = %s,
                    input_tokens = %s,
                    output_tokens = %s,
                    model_used = %s,
                    created_at = now()
                WHERE id = %s
                """,
                (result["generated_content"], result.get("input_tokens", 0),
                 result.get("output_tokens", 0), os.environ.get("OUTPUT_MODEL"),
                 str(output_id)),
            )
            
            cur.execute("DELETE FROM output_sources WHERE output_id = %s", (str(output_id),))
            from retrieval import find_relevant_notes
            relevant = find_relevant_notes(session["user_id"], topic_query)
            for n in relevant:
                cur.execute(
                    "INSERT INTO output_sources (output_id, note_id) VALUES (%s, %s)",
                    (str(output_id), n["id"]),
                )

            cur.execute("DELETE FROM output_sources WHERE output_id = %s", (str(result["id"]),))
            cur.execute("DELETE FROM outputs WHERE id = %s", (str(result["id"]),))

    return redirect(url_for("outputs.index"))


@outputs_bp.route("/<uuid:output_id>/pdf")
@require_login
def download_pdf(output_id):
    """Generate and serve a PDF on-the-fly using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        abort(500, "WeasyPrint is not installed. Run: pip install weasyprint")

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT output_type, topic_query, generated_content, created_at FROM outputs WHERE id = %s",
                (str(output_id),),
            )
            output = cur.fetchone()
            if output is None:
                abort(404)

    otype, topic, content, created = output

    escaped_content = (
        content.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace("\n", "<br>")
    )

    html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Georgia, 'Times New Roman', serif; line-height: 1.6; max-width: 700px; margin: 40px auto; padding: 0 20px; color: #222; }}
                h1 {{ font-size: 1.5em; border-bottom: 1px solid #ccc; padding-bottom: 8px; margin-bottom: 8px; }}
                .meta {{ color: #666; font-size: 0.9em; margin-bottom: 24px; }}
                .content {{ white-space: pre-wrap; word-wrap: break-word; }}
                @media print {{ body {{ margin: 0; padding: 20px; }} }}
            </style>
        </head>
        <body>
            <h1>{topic}</h1>
            <div class="meta">Type: {otype.capitalize()} | Generated: {created.strftime("%Y-%m-%d %H:%M")}</div>
            <div class="content">{escaped_content}</div>
        </body>
        </html>
    """

    pdf_bytes = HTML(string=html_content).write_pdf()
    safe_filename = f"{otype}_{topic[:30].replace(' ', '_').replace('/', '_')}.pdf"

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=safe_filename,
    )


@outputs_bp.route("/<uuid:output_id>/delete", methods=["POST"])
@require_login
def delete(output_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM outputs WHERE id = %s", (str(output_id),))
    return redirect(url_for("outputs.index"))