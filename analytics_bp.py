from flask import Blueprint, request, jsonify
from db import get_user_scoped_connection

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

@analytics_bp.route('/dashboard-data', methods=['GET'])
def get_all_dashboard_data():
    user_id = request.args.get('user_id')
    
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            # 1. Counts
            cur.execute("SELECT count(*) FROM notes WHERE user_id = %s", (user_id,))
            total_notes = cur.fetchone()[0] or 0
            cur.execute("SELECT count(*) FROM outputs WHERE user_id = %s", (user_id,))
            total_outputs = cur.fetchone()[0] or 0

            # 2. Heatmap
            cur.execute("SELECT DATE(created_at) as note_date, COUNT(*) FROM notes WHERE user_id = %s GROUP BY DATE(created_at)", (user_id,))
            notes_data = {str(row[0]): row[1] for row in cur.fetchall()}
            cur.execute("SELECT DATE(created_at) as out_date, COUNT(*) FROM outputs WHERE user_id = %s GROUP BY DATE(created_at)", (user_id,))
            outputs_data = {str(row[0]): row[1] for row in cur.fetchall()}

            # 3. Composition
            cur.execute("SELECT note_type, COUNT(*) FROM notes WHERE user_id = %s GROUP BY note_type", (user_id,))
            notes_comp_rows = cur.fetchall()
            cur.execute("SELECT output_type, COUNT(*) FROM outputs WHERE user_id = %s GROUP BY output_type", (user_id,))
            outputs_comp_rows = cur.fetchall()

            # 4. Quality Metrics
            cur.execute("SELECT count(*) FROM notes WHERE user_id = %s AND status = 'approved'", (user_id,))
            approved_notes = cur.fetchone()[0] or 0
            cur.execute("SELECT COALESCE(SUM(classify_input_tokens + classify_output_tokens), 0) FROM notes WHERE user_id = %s", (user_id,))
            classify_tokens = cur.fetchone()[0] or 0
            cur.execute("SELECT COALESCE(SUM(critic_input_tokens + critic_output_tokens), 0) FROM critique_sessions WHERE note_id IN (SELECT id FROM notes WHERE user_id = %s)", (user_id,))
            critique_tokens = cur.fetchone()[0] or 0
            cur.execute("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM outputs WHERE user_id = %s", (user_id,))
            output_tokens = cur.fetchone()[0] or 0

    # Process Heatmap
    all_dates = set(list(notes_data.keys()) + list(outputs_data.keys()))
    heatmap_data = [{"date": d, "notes": notes_data.get(d, 0), "outputs": outputs_data.get(d, 0), "count": notes_data.get(d, 0) + outputs_data.get(d, 0)} for d in sorted(list(all_dates))]

    # Process Composition
    notes_counts = {"claim": 0, "reflection": 0, "question": 0}
    for row in notes_comp_rows:
        if row[0] in notes_counts: notes_counts[row[0]] = row[1]
    notes_comp = [{"name": "Claims", "value": notes_counts["claim"]}, {"name": "Reflections", "value": notes_counts["reflection"]}, {"name": "Questions", "value": notes_counts["question"]}]

    outputs_counts = {"qna": 0, "narration": 0, "summary": 0}
    for row in outputs_comp_rows:
        if row[0] in outputs_counts: outputs_counts[row[0]] = row[1]
    outputs_comp = [{"name": "Q&A", "value": outputs_counts["qna"]}, {"name": "Narration", "value": outputs_counts["narration"]}, {"name": "Summary", "value": outputs_counts["summary"]}]

    # Process Metrics
    total_tokens = classify_tokens + critique_tokens + output_tokens
    total_note_tokens = classify_tokens + critique_tokens
    approval_rate = round((approved_notes / total_notes) * 100, 1) if total_notes > 0 else 0.0
    avg_tokens_notes = round(total_note_tokens / total_notes, 1) if total_notes > 0 else 0.0
    avg_tokens_outputs = round(output_tokens / total_outputs, 1) if total_outputs > 0 else 0.0

    # Return everything in one massive JSON object
    return jsonify({
        "counts": {"total_notes": total_notes, "total_outputs": total_outputs},
        "heatmap": heatmap_data,
        "notes_comp": notes_comp,
        "outputs_comp": outputs_comp,
        "metrics": {
            "approval_rate": approval_rate,
            "total_tokens": total_tokens,
            "avg_tokens_notes": avg_tokens_notes,
            "avg_tokens_outputs": avg_tokens_outputs
        }
    })