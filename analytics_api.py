from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from db import get_user_scoped_connection
from datetime import date

analytics_api = FastAPI()

analytics_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@analytics_api.get("/test")
async def test_endpoint():
    return {"message": "FastAPI is working!"}

@analytics_api.get("/total-notes")
def get_counts(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM notes WHERE user_id = %s", (user_id,))
            total_notes = cur.fetchone()[0] or 0
            
            cur.execute("SELECT count(*) FROM outputs WHERE user_id = %s", (user_id,))
            total_outputs = cur.fetchone()[0] or 0

    return {"total_notes": total_notes, "total_outputs": total_outputs}

@analytics_api.get("/heatmap-data")
def get_heatmap_data(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DATE(created_at) as note_date, COUNT(*) 
                FROM notes WHERE user_id = %s GROUP BY DATE(created_at)
            """, (user_id,))
            notes_data = {row[0]: row[1] for row in cur.fetchall()}
            
            cur.execute("""
                SELECT DATE(created_at) as out_date, COUNT(*) 
                FROM outputs WHERE user_id = %s GROUP BY DATE(created_at)
            """, (user_id,))
            outputs_data = {row[0]: row[1] for row in cur.fetchall()}

    all_dates = set(list(notes_data.keys()) + list(outputs_data.keys()))
    merged_data = []
    
    for d in sorted(list(all_dates)):
        n_count = notes_data.get(d, 0)
        o_count = outputs_data.get(d, 0)
        merged_data.append({
            "date": d.strftime('%Y-%m-%d'),
            "notes": n_count,
            "outputs": o_count,
            "count": n_count + o_count
        })
        
    return merged_data

@analytics_api.get("/composition-data")
def get_composition_data(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT note_type, COUNT(*) FROM notes WHERE user_id = %s GROUP BY note_type
            """, (user_id,))
            rows = cur.fetchall()
            
    counts = {"claim": 0, "reflection": 0, "question": 0}
    for row in rows:
        if row[0] in counts:
            counts[row[0]] = row[1]

    return [
        {"name": "Claims", "value": counts["claim"]},
        {"name": "Reflections", "value": counts["reflection"]},
        {"name": "Questions", "value": counts["question"]}
    ]

@analytics_api.get("/outputs-composition")
def get_outputs_composition(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT output_type, COUNT(*) FROM outputs WHERE user_id = %s GROUP BY output_type
            """, (user_id,))
            rows = cur.fetchall()
            
    counts = {"qna": 0, "narration": 0, "summary": 0}
    for row in rows:
        if row[0] in counts:
            counts[row[0]] = row[1]

    return [
        {"name": "Q&A", "value": counts["qna"]},
        {"name": "Narration", "value": counts["narration"]},
        {"name": "Summary", "value": counts["summary"]}
    ]

@analytics_api.get("/quality-metrics")
def get_quality_metrics(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM notes WHERE user_id = %s", (user_id,))
            total_notes = cur.fetchone()[0] or 0
            
            cur.execute("SELECT count(*) FROM outputs WHERE user_id = %s", (user_id,))
            total_outputs = cur.fetchone()[0] or 0

            cur.execute("SELECT count(*) FROM notes WHERE user_id = %s AND status = 'approved'", (user_id,))
            approved_notes = cur.fetchone()[0] or 0

            cur.execute("SELECT COALESCE(SUM(classify_input_tokens + classify_output_tokens), 0) FROM notes WHERE user_id = %s", (user_id,))
            classify_tokens = cur.fetchone()[0]

            # Using subquery to safely link critique sessions to the user's notes
            cur.execute("""
                SELECT COALESCE(SUM(critic_input_tokens + critic_output_tokens), 0) 
                FROM critique_sessions 
                WHERE note_id IN (SELECT id FROM notes WHERE user_id = %s)
            """, (user_id,))
            critique_tokens = cur.fetchone()[0]

            cur.execute("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM outputs WHERE user_id = %s", (user_id,))
            output_tokens = cur.fetchone()[0]

    total_tokens = classify_tokens + critique_tokens + output_tokens
    total_note_tokens = classify_tokens + critique_tokens
    
    approval_rate = round((approved_notes / total_notes) * 100, 1) if total_notes > 0 else 0.0
    avg_tokens_notes = round(total_note_tokens / total_notes, 1) if total_notes > 0 else 0.0
    avg_tokens_outputs = round(output_tokens / total_outputs, 1) if total_outputs > 0 else 0.0

    return {
        "approval_rate": approval_rate,
        "total_tokens": total_tokens,
        "avg_tokens_notes": avg_tokens_notes,
        "avg_tokens_outputs": avg_tokens_outputs
    }