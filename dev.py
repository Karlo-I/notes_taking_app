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
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Dev Login</title>
            <link rel="stylesheet" href="/static/css/style.css">
        </head>
        <body class="login-body">
            <div class="login-page">
                <div class="login-card">
                    <div class="login-icon">🛠️</div>
                    <h1 class="login-title">Developer Login</h1>
                    <p class="login-subtitle">Enter a display name to simulate a user session.</p>
                    <form method="post" class="login-links">
                        <input type="text" name="display_name" class="form-control" placeholder="e.g. test-user-1" required autofocus style="text-align: center;">
                        <button type="submit" class="btn">Log in</button>
                    </form>
                </div>
            </div>
        </body>
        </html>
        """

    display_name = request.form["display_name"]

    # oauth_provider='dev' keeps this on the exact same users table and the
    # exact same upsert as real providers -- everything downstream (session,
    # RLS) is identical either way; only how you arrive at a user_id differs.
    user_id = upsert_user("dev", display_name, display_name)

    session["user_id"] = str(user_id)
    return redirect(url_for("index"))