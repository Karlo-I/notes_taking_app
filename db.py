"""
Database access layer.

Every user-scoped query MUST go through get_user_scoped_connection(), never
a raw pool connection. This is what makes the RLS policies in schema.sql
actually isolate users -- see DESIGN.md section 6.

SET LOCAL only lasts for the current transaction, so a pooled connection
handed back afterward carries no leftover user context into the next
request. A plain SET would leak across requests on a reused connection --
this function exists specifically to make that bug structurally impossible
rather than something to remember not to do.
"""

import os
from contextlib import contextmanager

from psycopg2 import pool as pg_pool

_pool = pg_pool.SimpleConnectionPool(1, 10, dsn=os.environ["DATABASE_URL"])


@contextmanager
def get_user_scoped_connection(user_id):
    """
    Yields a connection with app.current_user_id set for this transaction
    only. Use for anything touching notes, note_versions, critique_sessions,
    critique_turns, note_links, outputs, or output_sources -- every table
    with an RLS policy in schema.sql.
    """
    conn = _pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL app.current_user_id = %s", (str(user_id),))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


@contextmanager
def get_unscoped_connection():
    """
    No user context set. The only legitimate use right now is the OAuth/dev
    login lookup against `users`, which by definition happens before a
    user_id exists to scope against -- see the RLS comment on `users` in
    schema.sql. Do not reach for this anywhere else.
    """
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def vector_literal(embedding):
    """
    psycopg2 doesn't know the pgvector type natively -- pass an embedding as
    text ("[0.1,0.2,...]") and cast it server-side instead. Shared here
    rather than duplicated, since review.py and retrieval.py both need it.
    """
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"