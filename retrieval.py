"""
Retrieval -- given a topic or question, finds the most relevant approved
notes to ground an output. Reuses the same embedding step as note ingestion
(embeddings.py), just pointed at a query string instead of a note's own
content, and the same status != 'merged' exclusion the integration agent
uses in review.py -- a merged-away note's content now lives in whatever it
merged into, not in the note itself.

Pure retrieval only -- no LLM call here, no writing to `outputs`. That's the
next piece, built on top of this.
"""

from db import get_user_scoped_connection, vector_literal
from embeddings import get_embedding

RETRIEVAL_LIMIT = 8  # more generous than the integration agent's candidate
                      # limit (5) -- grounding an output benefits from
                      # broader context than a single merge/link decision does
RETRIEVAL_MIN_SIMILARITY = 0.45  # same floor established from real test data
                                  # (see the FATCA/Chapter 4 embedding test)


def find_relevant_notes(user_id, query_text, limit=RETRIEVAL_LIMIT, min_similarity=RETRIEVAL_MIN_SIMILARITY):
    """
    Embeds the query and returns the closest approved notes by cosine
    similarity, ordered nearest first. Empty list is a valid result -- it
    means nothing in the knowledge base is meaningfully related to this
    query, not an error.
    """
    query_embedding = get_embedding(query_text)
    max_distance = 1 - min_similarity
    literal = vector_literal(query_embedding)

    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content, note_type FROM notes
                WHERE embedding IS NOT NULL
                  AND status != 'merged'
                  AND embedding <=> %s::vector <= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (literal, max_distance, literal, limit),
            )
            rows = cur.fetchall()

    return [{"id": str(r[0]), "content": r[1], "note_type": r[2]} for r in rows]