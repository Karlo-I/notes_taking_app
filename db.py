import os
import psycopg2
from contextlib import contextmanager
from psycopg2 import pool as pg_pool

_pool = pg_pool.SimpleConnectionPool(1, 20, dsn=os.environ["DATABASE_URL"])

@contextmanager
def get_user_scoped_connection(user_id):
    conn = _pool.getconn()
    discarded = False
    
    try:
        # Set the user context for Row Level Security
        with conn.cursor() as cur:
            cur.execute("SET LOCAL app.current_user_id = %s", (str(user_id),))
        yield conn
        
    except psycopg2.OperationalError:
        # When Neon closes the idle connection, discard it from the pool so we don't reuse it.
        _pool.putconn(conn, close=True)
        discarded = True
        raise
        
    except Exception:
        # For other errors (like SQL syntax), try to rollback normally
        try:
            conn.rollback()
        except psycopg2.InterfaceError:
            # If rollback fails because the connection is dead, discard it
            _pool.putconn(conn, close=True)
            discarded = True
        raise
        
    finally:
        # Only return the connection to the pool if it wasn't already discarded
        if not discarded and conn.closed == 0:
            _pool.putconn(conn)

@contextmanager
def get_unscoped_connection():
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
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"