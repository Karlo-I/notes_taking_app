"""
App factory. This is the one place that decides whether the dev login
bypass exists at all. APP_ENV must be explicitly "development" -- something
this security-sensitive shouldn't ride on Flask's own debug flag.
"""

import os
from dotenv import load_dotenv
from flask import Flask, redirect, request, session, url_for

# Force load .env file explicitly, preventing reloader quirks
load_dotenv()

def create_app():
    app = Flask(__name__)

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
        <html>
        <head>
            <link rel="stylesheet" href="/static/css/style.css">
            <style>
                body {{ 
                    display: flex; 
                    justify-content: center; 
                    align-items: center; 
                    height: 100vh; 
                    flex-direction: column; 
                    gap: 16px; 
                    background: var(--bg-body);
                    margin: 0;
                }}
                h1 {{ margin-bottom: 32px; font-weight: 600; }}
                .login-container {{ display: flex; flex-direction: column; gap: 12px; width: 280px; }}
            </style>
        </head>
        <body>
            <h1>Welcome to Your Knowledge Base</h1>
            <div class="login-container">
                {''.join(links)}
            </div>
        </body>
        </html>
        """

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    return app