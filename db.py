import os
import psycopg2
from contextlib import contextmanager
from psycopg2 import pool as pg_pool

_pool = pg_pool.SimpleConnectionPool(1, 20, dsn=os.environ["DATABASE_URL"])

@contextmanager
def get_user_scoped_connection(user_id):
    retries = 0
    while True:
        conn = _pool.getconn()
        try:
            # Set the user context for Row Level Security
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_user_id = %s", (str(user_id),))
            yield conn
            return # Exit generator on success
            
        except psycopg2.OperationalError:
            # Connection died (e.g., Render idle timeout)
            if retries >= 1:
                try: _pool.putconn(conn, close=True)
                except Exception: pass
                raise # Fail if it dies twice
                
            retries += 1
            try: _pool.putconn(conn, close=True) # Discard dead connection
            except Exception: pass
            continue # Loop to get a fresh connection
            
        except Exception:
            # For other errors (like SQL syntax), rollback normally
            try: conn.rollback()
            except psycopg2.InterfaceError:
                try: _pool.putconn(conn, close=True)
                except Exception: pass
            raise
            
        finally:
            # Only return to pool if we are exiting the generator (success or final failure)
            # If we are continuing the loop, conn.closed is already 1 from putconn(close=True) above.
            if conn and conn.closed == 0:
                _pool.putconn(conn)


@contextmanager
def get_unscoped_connection():
    retries = 0
    while True:
        conn = _pool.getconn()
        try:
            yield conn
            conn.commit()
            return # Exit generator on success
            
        except psycopg2.OperationalError:
            # Connection died
            if retries >= 1:
                try: _pool.putconn(conn, close=True)
                except Exception: pass
                raise 
                
            retries += 1
            try: _pool.putconn(conn, close=True)
            except Exception: pass
            continue 
            
        except Exception:
            try: conn.rollback()
            except psycopg2.InterfaceError:
                try: _pool.putconn(conn, close=True)
                except Exception: pass
            raise
            
        finally:
            if conn and conn.closed == 0:
                _pool.putconn(conn)


def vector_literal(embedding):
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"