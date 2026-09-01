"""
Topic Extraction -- runs after a note is approved.
Uses a cheap Haiku call to extract 1-3 broad topics and links them to the note.
"""

import json
import os
import anthropic
from db import get_user_scoped_connection

_CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_MODEL = "claude-haiku-4-5-20251001" # Matches your integration.py model

def extract_and_save_topics(user_id: str, note_id: str, content: str):
    """Extracts topics from a note and saves them to the DB. Fails silently if LLM errors."""

    # Convert IDs to strings so the database driver doesn't get confused
    user_id = str(user_id)
    note_id = str(note_id)
    
    prompt = f"""Analyze the following note and extract 1 to 3 core, high-level topics or concepts it belongs to.
Examples: 'US Withholding Tax', 'Career Strategy', 'Health & Fasting'.
Keep topics broad enough to group related sub-topics together.
Return ONLY a JSON array of strings. No other text, no markdown fences.

Note content:
{content}"""

    try:
        response = _CLIENT.messages.create(
            model=_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_text = response.content[0].text.strip()
        
        # Clean up potential markdown fences just in case
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.rstrip().endswith("```"):
                raw_text = raw_text.rstrip()[:-3]

        topics_list = json.loads(raw_text)
        if not isinstance(topics_list, list):
            return
    except Exception:
        # If the LLM fails or returns bad JSON, we just skip topic extraction.
        # We don't want to block the user from approving their note.
        return

    # Save to DB
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            for topic_name in topics_list:
                topic_name = topic_name.strip()
                if not topic_name: 
                    continue

                # Check if topic already exists for this user
                cur.execute("SELECT id FROM topics WHERE user_id = %s AND name = %s", (user_id, topic_name))
                row = cur.fetchone()

                if row:
                    topic_id = row[0]
                else:
                    cur.execute(
                        "INSERT INTO topics (user_id, name) VALUES (%s, %s) RETURNING id",
                        (user_id, topic_name)
                    )
                    topic_id = cur.fetchone()[0]

                # Link note to topic (ON CONFLICT DO NOTHING prevents duplicate links)
                cur.execute(
                    "INSERT INTO note_topics (note_id, topic_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (note_id, topic_id)
                )