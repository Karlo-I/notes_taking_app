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
            # ORDER BY still works perfectly with DOUBLE PRECISION floats
            cur.execute(
                "SELECT id, content, status, order_index, created_at "
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
                "created_at": row[4].strftime('%Y-%m-%d %H:%M') if row[4] else ''
            })

    return render_template("todos/index.html", todos=todos)


@todos_bp.route("/new", methods=["POST"])
@require_login
def create():
    """Create a new task. Returns JSON for seamless UI."""
    content = request.form.get("content", "").strip()
    if not content:
        abort(400)

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            # MAX + 1 still works perfectly for appending to the bottom of a float list
            cur.execute(
                "SELECT COALESCE(MAX(order_index), 0) + 1 FROM todo_items WHERE user_id = %s AND status = 'draft'",
                (session["user_id"],)
            )
            next_order = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO todo_items (user_id, content, status, order_index) VALUES (%s, %s, 'draft', %s) RETURNING id",
                (session["user_id"], content, next_order)
            )
            new_id = cur.fetchone()[0]
        conn.commit()

    return jsonify({
        "id": str(new_id),
        "content": content,
        "order_index": next_order
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
            # 1. Get the indices of the neighbors
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

            # 2. Calculate the new fractional index
            new_index = 0.0
            if prev_index is not None and next_index is not None:
                new_index = (prev_index + next_index) / 2.0
            elif prev_index is not None:
                new_index = prev_index + 1.0
            elif next_index is not None:
                new_index = next_index - 1.0
            else:
                new_index = 1.0 # Empty list

            # 3. Update ONLY the single item that was moved
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