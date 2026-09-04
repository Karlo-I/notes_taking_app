from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import get_unscoped_connection, get_user_scoped_connection

# Create the FastAPI app instance
analytics_api = FastAPI()

# Allow React to make requests from localhost
analytics_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=False, # Must be False when using "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

@analytics_api.get("/test")
async def test_endpoint():
    return {"message": "FastAPI is working!"}

@analytics_api.get("/total-notes")
def get_total_notes():
    total_count = 0
    
    # 1. Get a list of ALL user IDs from the database
    with get_unscoped_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users")
            user_ids = [row[0] for row in cur.fetchall()]

    # 2. Loop through each user and count their notes
    for uid in user_ids:
        with get_user_scoped_connection(uid) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM notes")
                total_count += cur.fetchone()[0]

    return {"total_notes": total_count}


@analytics_api.get("/resurfaced-thought")
def get_resurfaced_thought():
    try:
        # Get a list of all user IDs
        with get_unscoped_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users")
                user_ids = [row[0] for row in cur.fetchall()]
        
        # Collect one random approved note from each user
        all_notes = []
        for uid in user_ids:
            with get_user_scoped_connection(uid) as conn:
                with conn.cursor() as cur:
                    # Using the correct column name 'status' and value 'approved'
                    cur.execute("""
                        SELECT content, created_at, note_type 
                        FROM notes 
                        WHERE status = 'approved'
                        ORDER BY RANDOM() 
                        LIMIT 1
                    """)
                    note = cur.fetchone()
                    if note:
                        all_notes.append({
                            "content": note[0],
                            "created_at": note[1].isoformat() if note[1] else None,
                            "note_type": note[2]
                        })
        
        # If we found any notes, pick one randomly to display
        if all_notes:
            import random
            return random.choice(all_notes)
        
        return {"content": "No approved notes yet. Keep refining your thoughts!", "created_at": None, "note_type": None}
        
    except Exception as e:
        return {"error": str(e)}
    

@analytics_api.get("/heatmap-data")
def get_heatmap_data():
    # Get a list of all user IDs
    with get_unscoped_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users")
            user_ids = [row[0] for row in cur.fetchall()]
    
    # Collect all notes from all users
    all_notes = []
    for uid in user_ids:
        with get_user_scoped_connection(uid) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DATE(created_at) as note_date, COUNT(*) 
                    FROM notes 
                    GROUP BY DATE(created_at)
                    ORDER BY note_date
                """)
                rows = cur.fetchall()
                for row in rows:
                    date_obj = row[0]
                    count = row[1]
                    date_str = date_obj.strftime('%Y-%m-%d') if date_obj else None
                    all_notes.append({"date": date_str, "count": count})
    
    print(f"Total heatmap data points: {len(all_notes)}")
    return all_notes


@analytics_api.get("/composition-data")
def get_composition_data():
    with get_unscoped_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users")
            user_ids = [row[0] for row in cur.fetchall()]
    
    # Dictionary to hold counts
    counts = {"claim": 0, "reflection": 0, "question": 0}
    
    for uid in user_ids:
        with get_user_scoped_connection(uid) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT note_type, COUNT(*) 
                    FROM notes 
                    GROUP BY note_type
                """)
                rows = cur.fetchall()
                for row in rows:
                    note_type = row[0]
                    count = row[1]
                    if note_type in counts:
                        counts[note_type] += count

    # Format for Recharts
    return [
        {"name": "Claims", "value": counts["claim"]},
        {"name": "Reflections", "value": counts["reflection"]},
        {"name": "Questions", "value": counts["question"]}
    ]


@analytics_api.get("/quality-metrics")
def get_quality_metrics():
    with get_unscoped_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users")
            user_ids = [row[0] for row in cur.fetchall()]

    metrics = {
        "total_sessions": 0,
        "approved_sessions": 0,
        "total_turns": 0,
        "total_tokens": 0
    }

    for uid in user_ids:
        with get_user_scoped_connection(uid) as conn:
            with conn.cursor() as cur:
                # Get session counts AND sum of tokens
                cur.execute("""
                    SELECT 
                        COUNT(*),
                        COUNT(*) FILTER (WHERE resolution = 'approved'),
                        COALESCE(SUM(critic_input_tokens), 0) + COALESCE(SUM(critic_output_tokens), 0)
                    FROM critique_sessions
                """)
                row = cur.fetchone()
                if row:
                    metrics["total_sessions"] += row[0] or 0
                    metrics["approved_sessions"] += row[1] or 0
                    metrics["total_tokens"] += row[2] or 0

                # Get total turns
                cur.execute("SELECT COUNT(*) FROM critique_turns")
                turns = cur.fetchone()[0]
                metrics["total_turns"] += turns or 0

    # Calculate derived metrics safely
    total = metrics["total_sessions"]
    approval_rate = round((metrics["approved_sessions"] / total) * 100, 1) if total > 0 else 0.0
    avg_turns = round(metrics["total_turns"] / total, 1) if total > 0 else 0.0
    avg_tokens = round(metrics["total_tokens"] / total, 1) if total > 0 else 0.0

    return {
        "total_sessions": total,
        "approval_rate": approval_rate,
        "avg_turns": avg_turns,
        "avg_tokens": avg_tokens
    }