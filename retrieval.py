"""
Retrieval -- given a topic or question, finds the most relevant approved
notes to ground an output. Uses LLM query expansion for broad recall, 
and LLM re-ranking for high precision.
"""

import os
import json
import anthropic
from db import get_user_scoped_connection, vector_literal
from embeddings import get_embedding

_CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_EXPANDER_MODEL = "claude-haiku-4-5-20251001"

RETRIEVAL_LIMIT = 12  # Fetch more than we need for the re-ranker to choose from
RETRIEVAL_MIN_SIMILARITY = 0.20  # Low threshold for broad recall


def _expand_query(query_text: str) -> str:
    """Uses a cheap LLM to expand a query with relevant synonyms and sub-topics."""
    prompt = f"""The user is querying a personal knowledge base with: "{query_text}"
    Expand this query into a comma-separated list of specific sub-topics, technical terms, and related concepts that might appear in notes about this subject. 
    Return ONLY the comma-separated list. No intro, no outro. Max 100 words."""
    
    try:
        response = _CLIENT.messages.create(
            model=_EXPANDER_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        expanded_text = response.content[0].text.strip()
        return f"{query_text}, {expanded_text}"
    except Exception:
        return query_text


def _rerank_notes(query_text: str, notes: list) -> list:
    """
    Uses a cheap LLM to filter and rank note snippets. 
    Returns only the most relevant notes (max 8) to save context window space.
    """
    if not notes:
        return notes
    
    # Create short snippets to save tokens
    snippets = []
    for i, note in enumerate(notes):
        # Take first 250 chars and remove newlines to keep it compact
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
        
        # Clean markdown fences if the LLM adds them
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
            if raw_text.rstrip().endswith("```"):
                raw_text = raw_text.rstrip()[:-3]
        
        selected_indices = json.loads(raw_text)
        
        # Rebuild the list using only the selected indices
        reranked_notes = []
        for idx in selected_indices:
            if isinstance(idx, int) and 0 <= idx < len(notes):
                reranked_notes.append(notes[idx])
        
        return reranked_notes[:8] # Hard limit of 8
        
    except Exception as e:
        # If re-ranking fails, just return the first 8 notes from vector search
        print(f"Re-ranking failed, using fallback: {e}")
        return notes[:8]


def find_relevant_notes(user_id, query_text, limit=8, min_similarity=RETRIEVAL_MIN_SIMILARITY):
    """
    Main retrieval pipeline:
    1. Expand query for broad recall
    2. Vector search (fetching up to 12 candidates)
    3. LLM Re-ranking (filtering down to the best 8)
    """
    # Stage 1: Expand the query
    expanded_query = _expand_query(query_text)
    
    query_embedding = get_embedding(expanded_query)
    max_distance = 1 - min_similarity
    literal = vector_literal(query_embedding)

    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            # Stage 2: Broad Vector Search (fetching RETRIEVAL_LIMIT candidates)
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

    # Convert to list of dicts
    candidate_notes = [{"id": str(r[0]), "content": r[1], "note_type": r[2]} for r in rows]
    
    # Stage 3: Re-rank and filter
    final_notes = _rerank_notes(query_text, candidate_notes)

    return final_notes