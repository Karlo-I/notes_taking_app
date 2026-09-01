"""
Retrieval -- given a topic or question, finds the most relevant approved
notes to ground an output. Uses explicit topic filtering for broad recall 
of related sub-topics, followed by LLM re-ranking for high precision.
"""

import os
import json
import anthropic
from db import get_user_scoped_connection, vector_literal
from embeddings import get_embedding

_CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_EXPANDER_MODEL = "claude-haiku-4-5-20251001"

RETRIEVAL_LIMIT = 12  # Fetch candidates for the re-ranker
RETRIEVAL_MIN_SIMILARITY = 0.20  # Low threshold for broad recall within the topic


def _identify_topics(query_text: str, user_id: str) -> list:
    """
    Uses LLM to identify which broad topics from the user's KB are relevant
    to this query. Returns a list of topic UUIDs.
    """
    try:
        with get_user_scoped_connection(user_id) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM topics WHERE user_id = %s", (str(user_id),))
                all_topics = cur.fetchall()
        
        if not all_topics:
            return []
        
        topic_list = "\n".join([f"- {name} (ID: {tid})" for tid, name in all_topics])
        
        prompt = f"""The user is asking: "{query_text}"

Here are the topics in their knowledge base:
{topic_list}

Return ONLY a JSON array of the IDs of topics that are relevant to answering this query. If none are relevant, return an empty array []. 
Example output: ["123e4567-e89b-12d3-a456-426614174000"] or []"""

        response = _CLIENT.messages.create(
            model=_EXPANDER_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_text = response.content[0].text.strip()
        
        # Clean markdown fences if the LLM adds them
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.rstrip().endswith("```"):
                raw_text = raw_text.rstrip()[:-3]
        
        topic_ids = json.loads(raw_text)
        return topic_ids if isinstance(topic_ids, list) else []
    except Exception as e:
        print(f"Topic identification failed: {e}")
        return []


def _rerank_notes(query_text: str, notes: list) -> list:
    """
    Uses a cheap LLM to filter and rank note snippets. 
    Returns only the most relevant notes (max 8) to save context window space.
    """
    if not notes:
        return notes
    
    snippets = []
    for i, note in enumerate(notes):
        snippet = note['content'][:250].replace('\n', ' ')
        snippets.append(f"Index {i}: {snippet}")
    
    snippets_text = "\n".join(snippets)
    
    prompt = f"""Query: "{query_text}"

Here are retrieved note snippets:
{snippets_text}

Return ONLY a JSON array of the Index numbers (e.g., [0, 2, 4]) of the notes that are actually relevant to answering the query. Return at most 8 indices. Do not include irrelevant notes."""

    try:
        response = _CLIENT.messages.create(
            model=_EXPANDER_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        raw_text = response.content[0].text.strip()
        
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.rstrip().endswith("```"):
                raw_text = raw_text.rstrip()[:-3]
        
        selected_indices = json.loads(raw_text)
        
        reranked_notes = []
        for idx in selected_indices:
            if isinstance(idx, int) and 0 <= idx < len(notes):
                reranked_notes.append(notes[idx])
        
        return reranked_notes[:8]
        
    except Exception as e:
        print(f"Re-ranking failed, using fallback: {e}")
        return notes[:8]


def find_relevant_notes(user_id, query_text, limit=8, min_similarity=RETRIEVAL_MIN_SIMILARITY):
    """
    Main retrieval pipeline:
    1. Identify relevant topics from the query
    2. Vector search STRICTLY within those topics (ensures umbrella coverage)
    3. Fallback to pure vector search if no topics are identified
    4. LLM Re-ranking (filtering down to the best 8)
    """
    # Stage 1: Identify relevant topics
    relevant_topic_ids = _identify_topics(query_text, user_id)
    
    query_embedding = get_embedding(query_text)
    max_distance = 1 - min_similarity
    literal = vector_literal(query_embedding)

    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            if relevant_topic_ids:
                # Stage 2a: Filtered Vector Search within identified topics
                # Using DISTINCT ON to avoid the ORDER BY issue with DISTINCT
                cur.execute(
                    """
                    SELECT DISTINCT ON (n.id) n.id, n.content, n.note_type, 
                           (n.embedding <=> %s::vector) AS distance
                    FROM notes n
                    INNER JOIN note_topics nt ON n.id = nt.note_id
                    WHERE n.embedding IS NOT NULL
                      AND n.status != 'merged'
                      AND nt.topic_id = ANY(%s::uuid[])
                      AND n.embedding <=> %s::vector <= %s
                    ORDER BY n.id, distance
                    LIMIT %s
                    """,
                    (literal, relevant_topic_ids, literal, max_distance, RETRIEVAL_LIMIT),
                )
            else:
                # Stage 2b: Fallback to pure vector search
                cur.execute(
                    """
                    SELECT id, content, note_type FROM notes
                    WHERE embedding IS NOT NULL
                      AND status != 'merged'
                      AND embedding <=> %s::vector <= %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (literal, max_distance, literal, RETRIEVAL_LIMIT),
                )
            rows = cur.fetchall()

    # Convert to list of dicts (ignore the distance column we added)
    candidate_notes = [{"id": str(r[0]), "content": r[1], "note_type": r[2]} for r in rows]
    
    # Stage 3: Re-rank and filter
    final_notes = _rerank_notes(query_text, candidate_notes)

    return final_notes