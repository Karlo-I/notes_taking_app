"""
Topic Extraction -- runs after a note is approved.
Uses a cheap Haiku call to extract 1-3 broad topics and links them to the note.
"""

import json
import os
import anthropic
from db import get_user_scoped_connection

_CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_MODEL = "claude-haiku-4-5-20251001" 

def extract_and_save_topics(user_id: str, note_id: str, content: str):
    """Extracts topics from a note and saves them to the DB. Fails silently if LLM errors."""
    user_id = str(user_id)
    note_id = str(note_id)
    
    # 1. Fetch existing topics for this user to give the AI a "menu"
    existing_topics_list = []
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM topics WHERE user_id = %s", (user_id,))
            existing_topics_list = [row[0] for row in cur.fetchall()]

    # 2. Build the prompt with the menu
    menu_text = ""
    if existing_topics_list:
        # Limit to 50 to save tokens, and format as a clean list
        menu_text = f"\n\nEXISTING TOPICS IN DATABASE (Reuse these if they fit!):\n- " + "\n- ".join(existing_topics_list[:50])

    prompt = f"""Analyze the following note and extract 1 to 3 core, high-level topics or concepts it belongs to.
Keep topics broad enough to group related sub-topics together.
Return ONLY a JSON array of strings. No other text, no markdown fences.{menu_text}

Note content:
{content}"""

    try:
        response = _CLIENT.messages.create(
            model=_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_text = response.content[0].text.strip()
        
        # Clean up potential markdown fences
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.rstrip().endswith("```"):
                raw_text = raw_text.rstrip()[:-3]

        topics_list = json.loads(raw_text)
        if not isinstance(topics_list, list):
            return
    
    except Exception as e:
        print("TOPIC EXTRACTION ERROR:", e)
        return

    # 3. Save to DB (Reusing existing IDs if the name matches)
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            for topic_name in topics_list:
                topic_name = topic_name.strip()
                if not topic_name: 
                    continue

                # Check if topic already exists (Case-insensitive check is safer)
                cur.execute("SELECT id FROM topics WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (user_id, topic_name))
                row = cur.fetchone()

                if row:
                    topic_id = row[0]
                else:
                    cur.execute(
                        "INSERT INTO topics (user_id, name) VALUES (%s, %s) RETURNING id",
                        (user_id, topic_name)
                    )
                    topic_id = cur.fetchone()[0]

                # Link note to topic
                cur.execute(
                    "INSERT INTO note_topics (note_id, topic_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (note_id, topic_id)
                )

            conn.commit()