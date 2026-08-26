"""
Outputs blueprint -- create, view, list, delete generated outputs.

Also handles PDF export via WeasyPrint once that dependency is installed.
Every query goes through get_user_scoped_connection() so RLS enforces
isolation automatically -- no WHERE user_id = ... anywhere in this file.
"""

import html
import json
import os
from db import get_user_scoped_connection
from decorators import require_login
from flask import Blueprint, abort, redirect, request, send_file, session, url_for
from generate import generate_output, SYSTEM_PROMPTS
from io import BytesIO

outputs_bp = Blueprint("outputs", __name__, url_prefix="/outputs")


@outputs_bp.route("/")
@require_login
def index():
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, output_type, topic_query, created_at "
                "FROM outputs ORDER BY created_at DESC"
            )
            rows = cur.fetchall()

    def _row(r):
        oid, otype, topic, created = r[0], r[1], r[2], r[3]
        return (
            f'<li><a href="/outputs/{oid}">[{otype}] {topic[:70]}</a> '
            f'-- {created.strftime("%Y-%m-%d %H:%M")}</li>'
        )

    items = "".join(_row(r) for r in rows) if rows else "<li>No outputs yet.</li>"

    return f"""
        <p><a href="/">&larr; home</a></p>
        <h2>Your outputs</h2>
        <a href="/outputs/new">+ New output</a>
        <ul>{items}</ul>
    """


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
        abort(400, "Topic query is required.")
    if output_type not in SYSTEM_PROMPTS:
        abort(400, f"Invalid output_type: {output_type}")

    try:
        result = generate_output(session["user_id"], topic_query, output_type)
    except ValueError as e:
        # Re-render form with error message
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

    return redirect(url_for("outputs.view", output_id=result["id"]))


@outputs_bp.route("/<uuid:output_id>")
@require_login
def view(output_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, output_type, topic_query, generated_content, pdf_path, created_at "
                "FROM outputs WHERE id = %s",
                (str(output_id),),
            )
            output = cur.fetchone()
            if output is None:
                abort(404)

    oid, otype, topic, content, pdf_path, created = output

    pdf_link = f'<p><a href="/outputs/{oid}/pdf">Download PDF</a></p>'

    # Escape HTML in generated content for safe display
    escaped_content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

    return f"""
        <p><a href="/outputs">&larr; back</a></p>
        <p>Type: {otype} | Created: {created.strftime("%Y-%m-%d %H:%M")}</p>
        <h3>Topic: {topic}</h3>
        {pdf_link}
        <div style="white-space:pre-wrap; font-family:serif; line-height:1.6; max-width:700px;">
            {escaped_content}
        </div>
        <br>
        <div style="margin-top: 24px; display: flex; gap: 12px;">
            <form method="post" action="/outputs/{oid}/regenerate" style="display:inline;">
                <button type="submit">↻ Regenerate</button>
            </form>
            <button type="button" id="copy-btn-{oid}" onclick="copyToClipboard('{oid}')">
                Copy to Clipboard
            </button>
            <form method="post" action="/outputs/{oid}/delete" style="display:inline; margin-left:auto;">
                <button type="submit" style="color:red;">Delete</button>
            </form>
        </div>
        <script>
        function copyToClipboard(outputId) {{
            const content = {json.dumps(content)};
            navigator.clipboard.writeText(content).then(() => {{
                const btn = document.getElementById('copy-btn-' + outputId);
                btn.textContent = 'Copied!';
                setTimeout(() => {{
                    btn.textContent = 'Copy to Clipboard';
                }}, 1500);
            }});
        }}
        </script>
            """


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
        result = generate_output(session["user_id"], topic_query, output_type)
    except ValueError as e:
        return redirect(url_for("outputs.view", output_id=output_id))

    # Update the existing row instead of creating a new one
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
            # Delete old provenance and re-insert
            cur.execute("DELETE FROM output_sources WHERE output_id = %s", (str(output_id),))
            # Re-retrieve to get fresh source note IDs
            from retrieval import find_relevant_notes
            relevant = find_relevant_notes(session["user_id"], topic_query)
            for n in relevant:
                cur.execute(
                    "INSERT INTO output_sources (output_id, note_id) VALUES (%s, %s)",
                    (str(output_id), n["id"]),
                )

    return redirect(url_for("outputs.view", output_id=output_id))


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

    # Escape HTML entities in generated content for safe rendering
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
                body {{
                    font-family: Georgia, 'Times New Roman', serif;
                    line-height: 1.6;
                    max-width: 700px;
                    margin: 40px auto;
                    padding: 0 20px;
                    color: #222;
                }}
                h1 {{
                    font-size: 1.5em;
                    border-bottom: 1px solid #ccc;
                    padding-bottom: 8px;
                    margin-bottom: 8px;
                }}
                .meta {{
                    color: #666;
                    font-size: 0.9em;
                    margin-bottom: 24px;
                }}
                .content {{
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                @media print {{
                    body {{ margin: 0; padding: 20px; }}
                }}
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