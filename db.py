import os
from contextlib import contextmanager
from psycopg2 import pool as pg_pool

_pool = pg_pool.SimpleConnectionPool(1, 10, dsn=os.environ["DATABASE_URL"])

@contextmanager
def get_user_scoped_connection(user_id):
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