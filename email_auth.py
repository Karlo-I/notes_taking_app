import re
import uuid
import bcrypt
from flask import Blueprint, request, session, redirect, url_for, flash, render_template, current_app
from db import get_unscoped_connection
from extensions import limiter

email_auth_bp = Blueprint('email_auth', __name__, url_prefix='/auth/email')

# A small blocklist of the most common passwords to enforce modern security standards
COMMON_PASSWORDS = {
    "password", "12345678", "qwerty123", "123456789", "1234567890",
    "password1", "iloveyou", "admin123", "welcome1", "monkey123",
    "1234567", "dragon123", "master123", "qwerty1", "abc12345", "letmein"
}

@email_auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Guard clause: if already logged in, kick them to their notes
    if 'user_id' in session:
        return redirect(url_for('notes.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # 1. Basic Validation
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Invalid email format.", "error")
            return redirect(url_for('email_auth.register'))

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return redirect(url_for('email_auth.register'))

        if password.lower() in COMMON_PASSWORDS:
            flash("This password is too common. Please choose a stronger one.", "error")
            return redirect(url_for('email_auth.register'))

        # 2. Check if user exists & Hash Password
        with get_unscoped_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    flash("An account with this email already exists.", "error")
                    return redirect(url_for('email_auth.register'))

                # Hash the password using bcrypt (slow by design to prevent brute force)
                hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # We use NULL for oauth fields so the UNIQUE(oauth_provider, oauth_subject_id) constraint isn't violated
                cur.execute(
                    "INSERT INTO users (email, password_hash, oauth_provider, oauth_subject_id) VALUES (%s, %s, NULL, NULL) RETURNING id",
                    (email, hashed_pw)
                )
                user_id = cur.fetchone()[0]
            conn.commit()

        # 3. CRITICAL FIX: Clear any lingering session data before logging in
        session.clear()
        session['user_id'] = str(user_id)
        
        return redirect(url_for('notes.index'))

    return render_template('email_auth.html')

@email_auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    with get_unscoped_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
            user = cur.fetchone()

            # Generic error message to prevent User Enumeration attacks
            if not user or not bcrypt.checkpw(password.encode('utf-8'), user[1].encode('utf-8')):
                flash("Invalid email or password.", "error")
                return redirect(url_for('email_auth.register'))

            session['user_id'] = str(user[0])
            return redirect(url_for('notes.index'))