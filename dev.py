"""
Development-only login bypass.

This module is never imported by the production app factory (see
app/__init__.py) -- it structurally does not exist in prod, rather than
existing-but-disabled behind a flag. See DESIGN.md section 6.

Lets you log in as any named user instantly, no OAuth round trip. This is
what makes RLS testing possible locally: open two browser sessions, log in
as two different display names, confirm one can never see the other's
notes once notes routes exist.
"""

from flask import Blueprint, redirect, request, session, url_for
from oauth import upsert_user

dev_auth_bp = Blueprint("dev_auth", __name__)


@dev_auth_bp.route("/dev/login", methods=["GET", "POST"])
def dev_login():
    if request.method == "GET":
        return """
            <form method="post">
                <input name="display_name" placeholder="e.g. test-user-1">
                <button type="submit">Log in</button>
            </form>
        """

    display_name = request.form["display_name"]

    # oauth_provider='dev' keeps this on the exact same users table and the
    # exact same upsert as real providers -- everything downstream (session,
    # RLS) is identical either way; only how you arrive at a user_id differs.
    user_id = upsert_user("dev", display_name, display_name)

    session["user_id"] = str(user_id)
    return redirect(url_for("index"))