"""
Shared by any blueprint that needs an authenticated user -- notes routes,
and later the critic/output routes too. Keeps the session[\"user_id\"] check
in one place rather than repeated at the top of every view function.
"""

from flask import redirect, session, url_for
from functools import wraps


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped