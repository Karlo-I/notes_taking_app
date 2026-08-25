"""
Real OAuth login (Google/GitHub) via Authlib.

Each provider only gets registered if its two env vars are actually set --
this lets you finish one provider at a time (e.g. GitHub today, Google
later) without the app crashing on missing config. Unregistered providers
just 404 at /auth/<provider>/login instead of erroring at startup.

upsert_user() is the shared insert-or-update against `users` -- both this
module and app/auth/dev.py call it, so there's exactly one place that
defines what "log in" means at the database level.
"""

import os

from authlib.integrations.flask_client import OAuth
from flask import Blueprint, abort, redirect, session, url_for

from db import get_unscoped_connection

oauth_bp = Blueprint("oauth", __name__)
oauth = OAuth()


def init_oauth(app):
    """Called once from create_app(). Registers whichever providers have credentials."""
    oauth.init_app(app)

    if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    if os.environ.get("GITHUB_CLIENT_ID") and os.environ.get("GITHUB_CLIENT_SECRET"):
        oauth.register(
            name="github",
            client_id=os.environ["GITHUB_CLIENT_ID"],
            client_secret=os.environ["GITHUB_CLIENT_SECRET"],
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user"},
        )


def upsert_user(provider, subject_id, display_name):
    """
    Shared by app/auth/dev.py and this module. Same INSERT ... ON CONFLICT
    shape either way, since both ultimately write to the same users table
    keyed on (oauth_provider, oauth_subject_id).
    """
    with get_unscoped_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (oauth_provider, oauth_subject_id, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (oauth_provider, oauth_subject_id) DO UPDATE
                    SET display_name = EXCLUDED.display_name
                RETURNING id
                """,
                (provider, subject_id, display_name),
            )
            return cur.fetchone()[0]


@oauth_bp.route("/auth/<provider>/login")
def login(provider):
    client = oauth.create_client(provider)
    if client is None:
        abort(404)  # not a real provider, or its credentials aren't set in .env yet
    redirect_uri = url_for("oauth.callback", provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@oauth_bp.route("/auth/<provider>/callback")
def callback(provider):
    client = oauth.create_client(provider)
    if client is None:
        abort(404)

    token = client.authorize_access_token()

    if provider == "google":
        # authlib validates the id_token and populates this automatically
        # because we registered with the "openid" scope.
        profile = token["userinfo"]
        subject_id = profile["sub"]
        display_name = profile.get("name") or profile.get("email")
    elif provider == "github":
        profile = client.get("user").json()
        subject_id = str(profile["id"])
        display_name = profile.get("name") or profile.get("login")
    else:
        abort(404)

    user_id = upsert_user(provider, subject_id, display_name)
    session["user_id"] = str(user_id)
    return redirect(url_for("index"))