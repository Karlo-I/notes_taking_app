"""
To-Do List Module -- Create, read, update, delete, and reorder tasks.
Now uses Fractional Indexing for O(1) database updates.
"""

import re
from db import get_user_scoped_connection
from decorators import require_login
from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

todos_bp = Blueprint("todos", __name__, url_prefix="/todos")


@todos_bp.route("/")
@require_login
def index():
    """Fetch all tasks for the user and group them by status for the template."""
    todos = {"draft": [], "ongoing": [], "complete": []}
    
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content, status, order_index, created_at, due_date "
                "FROM todo_items WHERE user_id = %s "
                "ORDER BY status, order_index ASC, created_at DESC",
                (session["user_id"],)
            )
            rows = cur.fetchall()

    for row in rows:
        status = row[2]
        if status in todos:
            # Strip HTML tags from content for clean card display
            raw_content = row[1] if row[1] else ""
            text = raw_content

            # --- STEP 0: Fix Tab Characters ---
            text = text.replace('\t', '&nbsp;&nbsp;')
            # ----------------------------------

            # 1. Capture the "Empty Paragraph" (User hitting Enter twice) FIRST
            text = re.sub(r'<p>\s*<br\s*/?>\s*</p>', '\n\n', text)

            # Shared helper to detect indentation level from HTML tags
            def get_indent(tag):
                tag = tag.lower()
                if 'ql-indent-2' in tag or 'indent-2' in tag: return '&nbsp;&nbsp;&nbsp;&nbsp;'
                if 'ql-indent-1' in tag or 'indent-1' in tag: return '&nbsp;&nbsp;'
                if 'margin-left' in tag or 'padding-left' in tag: return '&nbsp;&nbsp;'
                return ''

            # 2. Handle ORDERED Lists (<ol>) - Generates 1., 2., 3.
            def process_ordered_list(match):
                ol_content = match.group(1)
                count = 1
                
                def replace_li_with_num(li_match):
                    nonlocal count
                    tag = li_match.group(0).lower()
                    indent = get_indent(tag)
                    if not indent: indent = '&nbsp;&nbsp;'
                    
                    result = f"{indent}{count}. "
                    count += 1
                    return result
                
                processed = re.sub(r'<li[^>]*>', replace_li_with_num, ol_content)
                processed = re.sub(r'</li>', '\n', processed)
                return processed

            text = re.sub(r'<ol[^>]*>(.*?)</ol>', process_ordered_list, text, flags=re.DOTALL)

            # 3. Handle UNORDERED Lists (<ul>) - Generates Bullets
            def process_unordered_list(match):
                ul_content = match.group(1)
                
                def replace_li_with_bullet(li_match):
                    tag = li_match.group(0).lower()
                    indent = get_indent(tag)
                    if not indent: return '&nbsp;&nbsp;• '
                    return f'{indent}• '
                
                processed = re.sub(r'<li[^>]*>', replace_li_with_bullet, ul_content)
                processed = re.sub(r'</li>', '\n', processed)
                return processed

            text = re.sub(r'<ul[^>]*>(.*?)</ul>', process_unordered_list, text, flags=re.DOTALL)

            # 4. FALLBACK: Catch any stray <li> tags that weren't inside <ol> or <ul>
            # This prevents the browser from adding default bullets if regex fails
            text = re.sub(r'<li[^>]*>', '&nbsp;&nbsp;• ', text)
            text = re.sub(r'</li>', '\n', text)
            text = re.sub(r'</?(?:ol|ul)[^>]*>', '', text) # Remove any remaining list tags

            # 5. Handle Paragraphs and their Indentation
            def replace_p(match):
                return get_indent(match.group(0))

            text = re.sub(r'<p[^>]*>', replace_p, text)
            text = re.sub(r'</p>', '\n', text)

            # 6. Handle <br>
            text = re.sub(r'<br\s*/?>', '\n', text)

            # 7. Strip any other remaining HTML tags
            text = re.sub(r'<[^>]+>', '', text)

            # 8. Clean up whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)

            # Split into lines
            lines = text.split('\n')
            cleaned_lines = [line.rstrip() for line in lines]
            text = '\n'.join(cleaned_lines)

            # Final trim
            clean_content = text.strip()
            
            todos[status].append({
                "id": str(row[0]),
                "content": clean_content,      # Clean text for the card
                "raw_content": raw_content,    # RAW HTML for the edit modal
                "order_index": row[3],
                "created_at": row[4].strftime('%d/%m/%Y %H:%M') if row[4] else '',
                "due_date": row[5].strftime('%d/%m/%Y') if row[5] else None
            })

    return render_template("todos/index.html", todos=todos)


@todos_bp.route("/new", methods=["POST"])
@require_login
def create():
    """Create a new task. Accepts status and due_date from modal."""
    content = request.form.get("content", "").strip()
    status = request.form.get("status", "draft").strip().lower()
    due_date = request.form.get("due_date") or None # Grab the date (or None if empty)

    # Validate status to prevent bad data
    if status not in ['draft', 'ongoing', 'complete']:
        status = 'draft'

    if not content:
        abort(400)

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            # Calculate next index for the SPECIFIC status chosen
            cur.execute(
                "SELECT COALESCE(MAX(order_index), 0) + 1 FROM todo_items WHERE user_id = %s AND status = %s",
                (session["user_id"], status)
            )
            next_order = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO todo_items (user_id, content, status, order_index, due_date) VALUES (%s, %s, %s, %s, %s) RETURNING id, due_date",
                (session["user_id"], content, status, next_order, due_date)
            )
            new_row = cur.fetchone()
            new_id = new_row[0]
            saved_due_date = new_row[1]
        conn.commit()

    return jsonify({
        "id": str(new_id),
        "content": content,
        "status": status,
        "order_index": next_order,
        "due_date": saved_due_date.strftime('%d/%m/%Y') if saved_due_date else None
    })


@todos_bp.route("/reorder", methods=["POST"])
@require_login
def reorder():
    """Update status and order_index using Fractional Indexing (O(1) DB operation)."""
    data = request.get_json()
    new_status = data.get("new_status")
    item_id = data.get("item_id")
    prev_id = data.get("prev_id")
    next_id = data.get("next_id")

    if not new_status or not item_id:
        abort(400)

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            prev_index = None
            next_index = None

            if prev_id:
                cur.execute("SELECT order_index FROM todo_items WHERE id = %s AND user_id = %s", (str(prev_id), session["user_id"]))
                row = cur.fetchone()
                if row: prev_index = row[0]

            if next_id:
                cur.execute("SELECT order_index FROM todo_items WHERE id = %s AND user_id = %s", (str(next_id), session["user_id"]))
                row = cur.fetchone()
                if row: next_index = row[0]

            new_index = 0.0
            if prev_index is not None and next_index is not None:
                new_index = (prev_index + next_index) / 2.0
            elif prev_index is not None:
                new_index = prev_index + 1.0
            elif next_index is not None:
                new_index = next_index - 1.0
            else:
                new_index = 1.0

            cur.execute(
                "UPDATE todo_items SET status = %s, order_index = %s WHERE id = %s AND user_id = %s",
                (new_status, new_index, str(item_id), session["user_id"])
            )
        conn.commit()

    return jsonify({"success": True})


@todos_bp.route("/<uuid:todo_id>/delete", methods=["POST"])
@require_login
def delete(todo_id):
    """Delete a task."""
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM todo_items WHERE id = %s AND user_id = %s",
                (str(todo_id), session["user_id"])
            )
        conn.commit()

    return redirect(url_for("todos.index"))


@todos_bp.route("/<uuid:todo_id>/edit", methods=["POST"])
@require_login
def update(todo_id):
    """Update an existing task."""
    content = request.form.get("content", "").strip()
    status = request.form.get("status", "draft").strip().lower()
    due_date = request.form.get("due_date") or None

    if status not in ['draft', 'ongoing', 'complete']:
        status = 'draft'

    if not content:
        abort(400)

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE todo_items SET content = %s, status = %s, due_date = %s WHERE id = %s AND user_id = %s",
                (content, status, due_date, str(todo_id), session["user_id"])
            )
        conn.commit()

    return jsonify({"success": True})


@todos_bp.route("/clear-completed", methods=["POST"])
@require_login
def clear_completed():
    """Delete all tasks in the 'complete' status for the current user."""
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM todo_items WHERE user_id = %s AND status = 'complete'",
                (session["user_id"],)
            )
        conn.commit()
    return jsonify({"success": True})