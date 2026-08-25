"""
Admin routes -- completely hidden from normal users.
Only accessible when ADMIN_ENABLED=true is set in .env.
"""

import os
from flask import Blueprint, abort, session
from db import get_user_scoped_connection
from decorators import require_login

admin_bp = Blueprint("admin", __name__, url_prefix="/_admin")

@admin_bp.route("/outputs/costs")
@require_login
def output_costs():
    # Security checks
    if os.environ.get("ADMIN_ENABLED") != "true":
        abort(404)
    if session.get("user_id") != os.environ.get("ADMIN_USER_ID", ""):
        abort(404)

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            # 1. Fetch Output rows
            cur.execute("""
                SELECT id, output_type, topic_query, input_tokens, output_tokens, 
                       model_used, created_at 
                FROM outputs ORDER BY created_at DESC
            """)
            out_rows = cur.fetchall()

            # 2. Fetch Note rows (Input Pipeline)
            cur.execute("""
                SELECT id, note_type, LEFT(content, 40), 
                       (classify_input_tokens + integration_input_tokens), 
                       (classify_output_tokens + integration_output_tokens), 
                       created_at 
                FROM notes ORDER BY created_at DESC
            """)
            note_rows = cur.fetchall()

            # 3. Fetch Critique rows (Critic Pipeline)
            cur.execute("""
                SELECT started_at, resolution, note_id, critic_input_tokens, critic_output_tokens, id 
                FROM critique_sessions ORDER BY started_at DESC
            """)
            crit_rows = cur.fetchall()

            # 4. Calculate Aggregates for the Header
            cur.execute("SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) FROM outputs")
            out_inp, out_out = cur.fetchone()
            
            cur.execute("SELECT COALESCE(SUM(classify_input_tokens + integration_input_tokens), 0), COALESCE(SUM(classify_output_tokens + integration_output_tokens), 0) FROM notes")
            note_inp, note_out = cur.fetchone()
            
            cur.execute("SELECT COALESCE(SUM(critic_input_tokens), 0), COALESCE(SUM(critic_output_tokens), 0) FROM critique_sessions")
            crit_inp, crit_out = cur.fetchone()

    # Cost Calculations (Sonnet: $3/$15, Haiku: $0.80/$4.00 per 1M)
    out_cost = (out_inp * 3 + out_out * 15) / 1_000_000
    note_cost = (note_inp * 0.80 + note_out * 4.00) / 1_000_000
    crit_cost = (crit_inp * 0.80 + crit_out * 4.00) / 1_000_000
    total_cost = out_cost + note_cost + crit_cost
    total_inp = out_inp + note_inp + crit_inp
    total_out = out_out + note_out + crit_out

    # Helper to format table rows
    def _make_row(r, is_output=True):
        if is_output:
            oid, otype, topic, inp, out, model, created = r
            cost = (inp * 3 + out * 15) / 1_000_000
            return f"<tr><td>{created.strftime('%m-%d %H:%M')}</td><td>{otype}</td><td>{topic[:40] if topic else ''}</td><td>{model}</td><td>{inp:,}</td><td>{out:,}</td><td>${cost:.4f}</td></tr>"
        else:
            # For notes/critique, model is implicitly Haiku
            oid, otype, topic, inp, out, created = r
            cost = (inp * 0.80 + out * 4.00) / 1_000_000
            # Handle both datetime objects and strings
            if hasattr(created, 'strftime'):
                date_str = created.strftime('%m-%d %H:%M')
            else:
                # If it's already a string, just use it (or parse it if needed)
                date_str = str(created)[:16]  # Takes first 16 chars e.g. "2026-08-25 22:24"
                
            return f"<tr><td>{date_str}</td><td>{otype}</td><td>{topic}</td><td>Haiku</td><td>{inp:,}</td><td>{out:,}</td><td>${cost:.4f}</td></tr>"

    out_table = "".join(_make_row(r, True) for r in out_rows) if out_rows else "<tr><td colspan='7'>No outputs yet.</td></tr>"
    note_table = "".join(_make_row(r, False) for r in note_rows) if note_rows else "<tr><td colspan='7'>No notes processed yet.</td></tr>"
    crit_table = "".join(_make_row(r, False) for r in crit_rows) if crit_rows else "<tr><td colspan='7'>No critique sessions yet.</td></tr>"

    return f"""
        <p><a href="/">&larr; home</a></p>
        <h2>Complete AI Cost Dashboard</h2>
        
        <h3>Pipeline Breakdown</h3>
        <p><b>Total Cost: ${total_cost:.4f}</b> | Total Tokens: Input: {total_inp:,} | Output: {total_out:,}</p>
        <ul>
            <li><b>Output Pipeline (Sonnet):</b> ${out_cost:.4f}</li>
            <li><b>Input Pipeline (Haiku):</b> ${note_cost:.4f}</li>
            <li><b>Critic Pipeline (Haiku):</b> ${crit_cost:.4f}</li>
        </ul>

        <h3>1. Output Generations</h3>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%; margin-bottom: 20px;">
            <thead><tr><th>Created</th><th>Type</th><th>Topic</th><th>Model</th><th>Input</th><th>Output</th><th>Cost</th></tr></thead>
            <tbody>{out_table}</tbody>
        </table>

        <h3>2. Note Processing (Input Pipeline)</h3>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%; margin-bottom: 20px;">
            <thead><tr><th>Created</th><th>Type</th><th>Content Preview</th><th>Model</th><th>Input</th><th>Output</th><th>Cost</th></tr></thead>
            <tbody>{note_table}</tbody>
        </table>

        <h3>3. Critique Sessions</h3>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
            <thead><tr><th>Started</th><th>Resolution</th><th>Note ID</th><th>Model</th><th>Input</th><th>Output</th><th>Cost</th></tr></thead>
            <tbody>{crit_table}</tbody>
        </table>
    """