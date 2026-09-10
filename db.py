"""
Database access layer.
"""
import os
import psycopg2
from contextlib import contextmanager
from psycopg2 import pool as pg_pool

# Use ThreadedConnectionPool for thread-safe web environments (Gunicorn/a2wsgi)
_pool = pg_pool.ThreadedConnectionPool(1, 10, dsn=os.environ["DATABASE_URL"])


@contextmanager
def get_user_scoped_connection(user_id):
    """
    Yields a connection with app.current_user_id set for this transaction only.
    """
    conn = _pool.getconn()
    try:
        # Force transaction mode so SET LOCAL works reliably
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL app.current_user_id = %s", (str(user_id),))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Reset autocommit and safely return to pool to prevent leaks
        conn.autocommit = True
        _pool.putconn(conn)


@contextmanager
def get_unscoped_connection():
    """
    No user context set. Used only for OAuth/dev login lookup.
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
    Formats an embedding array as a PostgreSQL vector literal string.
    """
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"