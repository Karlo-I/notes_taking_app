"""
To-Do List Module -- Create, read, update, delete, and reorder tasks.
Now uses Fractional Indexing for O(1) database updates.
"""

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
            todos[status].append({
                "id": str(row[0]),
                "content": row[1],
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