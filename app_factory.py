"""
App factory. This is the one place that decides whether the dev login
bypass exists at all. APP_ENV must be explicitly "development" -- something
this security-sensitive shouldn't ride on Flask's own debug flag.
"""

import os
from dotenv import load_dotenv
from flask import Flask, redirect, request, session, url_for
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from a2wsgi import ASGIMiddleware
from analytics_api import analytics_api

# Force load .env file explicitly, preventing reloader quirks
load_dotenv()

def create_app():
    app = Flask(__name__)

    # Mount FastAPI under /api/analytics
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        '/api/analytics': ASGIMiddleware(analytics_api)
    })

    @app.after_request
    def prevent_caching(response):
        """
        Prevents the browser from caching pages. 
        This ensures that hitting the "Back" button after logout 
        forces a server check and redirects to login, rather than 
        showing a cached version of the protected page.
        """
        # Only apply to HTML pages, let the browser cache static CSS/JS/images for speed
        if response.content_type.startswith('text/html'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

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
            # Seamless redirect: logged-in users go straight to their notes
            return redirect(url_for("notes.index"))
        
        # Public landing page (only shown when NOT logged in)
        links = [
            '<a href="/auth/google/login" class="btn">Log in with Google</a>',
            '<a href="/auth/github/login" class="btn">Log in with GitHub</a>',
        ]
        if os.environ.get("APP_ENV") == "development":
            links.append('<a href="/dev/login" class="btn btn-secondary">Dev Login</a>')
        
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Knowledge Base — Login</title>
            <link rel="stylesheet" href="/static/css/style.css">
        </head>
        <body class="login-body">
            <div class="login-page">
                <div class="login-card">
                    <div class="login-icon">🧠</div>
                    <h1 class="login-title">Welcome to Your Knowledge Base</h1>
                    <p class="login-subtitle">Sharpen your thinking before it's recorded. Sign in to continue.</p>
                    <div class="login-links">
                        {''.join(links)}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    return app