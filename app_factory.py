"""
App factory. This is the one place that decides whether the dev login
bypass exists at all. APP_ENV must be explicitly "development" -- something
this security-sensitive shouldn't ride on Flask's own debug flag.
"""

import os
from dotenv import load_dotenv
from flask import Flask, redirect, session, url_for

# Force load .env file explicitly, preventing reloader quirks
load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    if os.environ.get("APP_ENV") == "development":
        from dev import dev_auth_bp

        app.register_blueprint(dev_auth_bp)

    from oauth import init_oauth, oauth_bp

    init_oauth(app)
    app.register_blueprint(oauth_bp)

    from notes import notes_bp

    app.register_blueprint(notes_bp)

    from review import review_bp

    app.register_blueprint(review_bp)

    # Outputs blueprint
    from outputs import outputs_bp

    app.register_blueprint(outputs_bp)

    # Conditionally register hidden admin blueprint
    if os.environ.get("ADMIN_ENABLED") == "true":
        from admin import admin_bp
        app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        if "user_id" in session:
            return (
                f"Logged in as user {session['user_id']}<br>"
                '<a href="/notes">Your notes</a><br>'
                '<a href="/outputs">Your outputs</a><br>'
                '<a href="/logout">Log out</a>'
            )
        links = [
            '<a href="/auth/google/login">Log in with Google</a>',
            '<a href="/auth/github/login">Log in with GitHub</a>',
        ]
        if os.environ.get("APP_ENV") == "development":
            links.append('<a href="/dev/login">Dev login</a>')
        return "Not logged in.<br>" + "<br>".join(links)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    return app