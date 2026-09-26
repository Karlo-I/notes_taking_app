import os
import psycopg2
from contextlib import contextmanager
from psycopg2 import pool as pg_pool

_pool = pg_pool.SimpleConnectionPool(1, 20, dsn=os.environ["DATABASE_URL"])

@contextmanager
def get_user_scoped_connection(user_id):
    conn = _pool.getconn()
    is_retry = False
    
    try:
        # Set the user context for Row Level Security
        with conn.cursor() as cur:
            cur.execute("SET LOCAL app.current_user_id = %s", (str(user_id),))
        yield conn
        
    except psycopg2.OperationalError:
        if not is_retry:
            # 1. The connection is dead (e.g., Render/Neon idle timeout). Discard it.
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
            
            # 2. Get a brand new connection and try exactly one more time
            conn = _pool.getconn()
            is_retry = True
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_user_id = %s", (str(user_id),))
            yield conn
        else:
            # If it fails twice, the database is actually down. Let it crash.
            raise
            
    except Exception:
        # For other errors (like SQL syntax), try to rollback normally
        try:
            conn.rollback()
        except psycopg2.InterfaceError:
            # If rollback fails because the connection is dead, discard it
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
            conn = None # Prevent the finally block from returning a dead connection
        raise
        
    finally:
        # Only return the connection to the pool if it's still alive
        if conn and conn.closed == 0:
            _pool.putconn(conn)


@contextmanager
def get_unscoped_connection():
    """Added retry logic to match get_user_scoped_connection and prevent OAuth crashes."""
    conn = _pool.getconn()
    is_retry = False
    
    try:
        yield conn
        conn.commit()
        
    except psycopg2.OperationalError:
        if not is_retry:
            # 1. The connection is dead (e.g., Render/Neon idle timeout). Discard it.
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
            
            # 2. Get a brand new connection and try exactly one more time
            conn = _pool.getconn()
            is_retry = True
            yield conn
            conn.commit()
        else:
            # If it fails twice, the database is actually down. Let it crash.
            raise
            
    except Exception:
        # For other errors, try to rollback normally
        try:
            conn.rollback()
        except psycopg2.InterfaceError:
            # If rollback fails because the connection is dead, discard it
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
            conn = None # Prevent the finally block from returning a dead connection
        raise
        
    finally:
        # Only return the connection to the pool if it's still alive
        if conn and conn.closed == 0:
            _pool.putconn(conn)


def vector_literal(embedding):
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"