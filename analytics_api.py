from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from db import get_user_scoped_connection
from datetime import date

# Create the FastAPI app instance
analytics_api = FastAPI()

# Allow React to make requests from localhost
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

# 1. COUNTS (Notes & Outputs)
@analytics_api.get("/total-notes")
def get_counts(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM notes")
            total_notes = cur.fetchone()[0] or 0
            
            cur.execute("SELECT count(*) FROM outputs")
            total_outputs = cur.fetchone()[0] or 0

    return {"total_notes": total_notes, "total_outputs": total_outputs}

# 2. HEATMAP DATA (Combined but distinct)
@analytics_api.get("/heatmap-data")
def get_heatmap_data(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            # Get Notes counts per day
            cur.execute("""
                SELECT DATE(created_at) as note_date, COUNT(*) 
                FROM notes GROUP BY DATE(created_at)
            """)
            notes_data = {row[0]: row[1] for row in cur.fetchall()}
            
            # Get Outputs counts per day
            cur.execute("""
                SELECT DATE(created_at) as out_date, COUNT(*) 
                FROM outputs GROUP BY DATE(created_at)
            """)
            outputs_data = {row[0]: row[1] for row in cur.fetchall()}

    # Merge the two dictionaries
    all_dates = set(list(notes_data.keys()) + list(outputs_data.keys()))
    merged_data = []
    
    for d in sorted(list(all_dates)):
        n_count = notes_data.get(d, 0)
        o_count = outputs_data.get(d, 0)
        merged_data.append({
            "date": d.strftime('%Y-%m-%d'),
            "notes": n_count,
            "outputs": o_count,
            "count": n_count + o_count # Total used for the color intensity
        })
        
    return merged_data

# 3. NOTES COMPOSITION
@analytics_api.get("/composition-data")
def get_composition_data(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT note_type, COUNT(*) FROM notes GROUP BY note_type
            """)
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

# 4. OUTPUTS COMPOSITION (New)
@analytics_api.get("/outputs-composition")
def get_outputs_composition(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT output_type, COUNT(*) FROM outputs GROUP BY output_type
            """)
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

# 5. QUALITY & COST METRICS
@analytics_api.get("/quality-metrics")
def get_quality_metrics(user_id: str = Query(...)):
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            # A. Get Counts
            cur.execute("SELECT count(*) FROM notes")
            total_notes = cur.fetchone()[0] or 0
            
            cur.execute("SELECT count(*) FROM outputs")
            total_outputs = cur.fetchone()[0] or 0

            cur.execute("SELECT count(*) FROM notes WHERE status = 'approved'")
            approved_notes = cur.fetchone()[0] or 0

            # B. Get Token Sums
            # 1. Note Classification Tokens
            cur.execute("SELECT COALESCE(SUM(classify_input_tokens + classify_output_tokens), 0) FROM notes")
            classify_tokens = cur.fetchone()[0]

            # 2. Critique Session Tokens
            cur.execute("SELECT COALESCE(SUM(critic_input_tokens + critic_output_tokens), 0) FROM critique_sessions")
            critique_tokens = cur.fetchone()[0]

            # 3. Output Generation Tokens
            cur.execute("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM outputs")
            output_tokens = cur.fetchone()[0]

    # Calculations
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