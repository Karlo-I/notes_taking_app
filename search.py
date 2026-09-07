"""
Global Search -- searches across both Notes and Outputs.
"""
from flask import Blueprint, jsonify, render_template, request, session
from db import get_user_scoped_connection
from decorators import require_login

search_bp = Blueprint("search", __name__)

# 1. The Main Search Page Route (Loads the HTML)
@search_bp.route("/search")
@require_login
def search():
    query = request.args.get("q", "").strip()
    notes_results = []
    outputs_results = []
    
    if query:
        search_term = f"%{query}%"
        with get_user_scoped_connection(session["user_id"]) as conn:
            with conn.cursor() as cur:
                # Search Notes
                cur.execute(
                    "SELECT id, note_type, content, status, created_at FROM notes WHERE content ILIKE %s ORDER BY created_at DESC",
                    (search_term,)
                )
                notes_results = cur.fetchall()
                
                # Search Outputs
                cur.execute(
                    "SELECT id, output_type, generated_content, created_at FROM outputs WHERE generated_content ILIKE %s ORDER BY created_at DESC",
                    (search_term,)
                )
                outputs_results = cur.fetchall()
                
    return render_template("search.html", query=query, notes=notes_results, outputs=outputs_results)

# 2. The Live Search API Route (Powers the Autocomplete Dropdown)
@search_bp.route("/api/search-suggestions")
@require_login
def search_suggestions():
    """Return search results as JSON for autocomplete"""
    query = request.args.get("q", "").strip()
    
    if len(query) < 2:
        return jsonify({"notes": [], "outputs": []})
    
    notes_results = []
    outputs_results = []
    search_term = f"%{query}%"
    
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            # Search Notes (limit to 5 for performance)
            cur.execute(
                """
                SELECT id, note_type, content, created_at 
                FROM notes 
                WHERE content ILIKE %s 
                ORDER BY created_at DESC 
                LIMIT 5
                """,
                (search_term,)
            )
            notes_results = [
                {
                    "id": str(row[0]),
                    "type": row[1],
                    "content": row[2][:150],
                    "created_at": row[3].strftime('%Y-%m-%d %H:%M') if row[3] else '',
                    "source": "note"
                }
                for row in cur.fetchall()
            ]
            
            # Search Outputs (limit to 5 for performance)
            cur.execute(
                """
                SELECT id, output_type, generated_content, created_at 
                FROM outputs 
                WHERE generated_content ILIKE %s 
                ORDER BY created_at DESC 
                LIMIT 5
                """,
                (search_term,)
            )
            outputs_results = [
                {
                    "id": str(row[0]),
                    "type": row[1],
                    "content": row[2][:150],
                    "created_at": row[3].strftime('%Y-%m-%d %H:%M') if row[3] else '',
                    "source": "output"
                }
                for row in cur.fetchall()
            ]
    
    return jsonify({
        "notes": notes_results,
        "outputs": outputs_results
    })