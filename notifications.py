from db import get_user_scoped_connection
from decorators import require_login
from flask import Blueprint, jsonify, request, session

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.route('/api/save-push-subscription', methods=['POST'])
@require_login
def save_push_subscription():
    data = request.json
    endpoint = data.get('endpoint')
    keys = data.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')

    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Invalid subscription data'}), 400

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            # Upsert: Insert new, or update keys if endpoint already exists
            cur.execute(
                """
                INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (endpoint) 
                DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth, user_id = EXCLUDED.user_id
                """,
                (session["user_id"], endpoint, p256dh, auth)
            )
        conn.commit()
        
    return jsonify({'status': 'success'}), 200

@notifications_bp.route('/api/delete-push-subscription', methods=['POST'])
@require_login
def delete_push_subscription():
    data = request.json
    endpoint = data.get('endpoint')
    
    if not endpoint:
        return jsonify({'error': 'Missing endpoint'}), 400

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s",
                (session["user_id"], endpoint)
            )
        conn.commit()
        
    return jsonify({'status': 'success'}), 200