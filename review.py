"""
The critic dialogue loop -- starting a review, exchanging turns with the
critic (critic.py), and resolving it via approve or override. See README.md
section 3 for the design rationale.

Every route here holds two separate transactions around each LLM call
rather than one long one: write to the DB, close the connection, call the
critic (a slow network request), then open a new connection to write the
result. Never hold a pooled connection open while waiting on Anthropic.
"""

from critic import get_critic_reply
from db import get_user_scoped_connection, vector_literal
from decorators import require_login
from embeddings import get_embedding
from flask import Blueprint, abort, redirect, request, session, url_for
from integration import decide as integration_decide

review_bp = Blueprint("review", __name__, url_prefix="/notes")

TURN_CAP = 4  # how many times the critic pushes back before handing control to the user
CANDIDATE_LIMIT = 5  # how many similar notes the integration agent gets to choose among


def embed_and_store(note_id, content):
    """
    Called from approve() for claims/reflections, and directly from
    notes.new() for questions (which skip critique entirely). This is the
    "embedding happens after approval, not before" decision from README.md:
    unreviewed notes never enter the searchable space.
    """
    embedding = get_embedding(content)
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE notes SET embedding = %s::vector WHERE id = %s",
                (vector_literal(embedding), str(note_id)),
            )
    return embedding


def _find_candidates(note_id, embedding):
    """
    Nearest existing notes by cosine distance, excluding the note itself and
    anything already merged away (its content now lives elsewhere).
    """
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content FROM notes
                WHERE embedding IS NOT NULL AND status != 'merged' AND id != %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (str(note_id), vector_literal(embedding), CANDIDATE_LIMIT),
            )
            rows = cur.fetchall()
    return [{"id": str(r[0]), "content": r[1]} for r in rows]


def _merge_into(target_id, new_note_id, merged_content):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM notes WHERE id = %s", (target_id,))
            row = cur.fetchone()
            if row is None:
                return  # target vanished somehow -- bail safely, leave the new note as-is
            old_content = row[0]

            cur.execute(
                "SELECT COALESCE(MAX(version_number), 0) FROM note_versions WHERE note_id = %s",
                (target_id,),
            )
            next_version = cur.fetchone()[0] + 1

            # Preserve the target's pre-merge content before overwriting it --
            # nothing is ever lost, only versioned. See README.md section 4.
            cur.execute(
                "INSERT INTO note_versions (note_id, version_number, content) VALUES (%s, %s, %s)",
                (target_id, next_version, old_content),
            )
            cur.execute(
                "UPDATE notes SET content = %s, status = 'approved_merged' WHERE id = %s",
                (merged_content, target_id),
            )
            cur.execute(
                "UPDATE notes SET status = 'merged', merged_into = %s WHERE id = %s",
                (target_id, str(new_note_id)),
            )

    # Target's content just changed -- its embedding is now stale. Recompute
    # it, same as any other approved note.
    new_embedding = get_embedding(merged_content)
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE notes SET embedding = %s::vector WHERE id = %s",
                (vector_literal(new_embedding), target_id),
            )


def run_integration(note_id, content, embedding):
    candidates = _find_candidates(note_id, embedding)
    result = integration_decide(content, candidates)

    # Extract and save integration token usage
    inp_tokens = result.get("input_tokens", 0)
    out_tokens = result.get("output_tokens", 0)
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE notes SET integration_input_tokens = %s, integration_output_tokens = %s WHERE id = %s",
                (inp_tokens, out_tokens, str(note_id)),
            )

    if result["decision"] == "merge" and result.get("target_note_id"):
        _merge_into(result["target_note_id"], note_id, result["merged_content"])
    elif result["decision"] == "link" and result.get("target_note_id"):
        with get_user_scoped_connection(session["user_id"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO note_links (note_id, related_note_id, link_type) VALUES (%s, %s, 'related')",
                    (str(note_id), result["target_note_id"]),
                )
    # decision == "new" -> nothing further to do, the note already stands alone


def _open_session_id(cur, note_id):
    cur.execute(
        """
        SELECT id FROM critique_sessions
        WHERE note_id = %s AND resolution IS NULL
        ORDER BY started_at DESC LIMIT 1
        """,
        (str(note_id),),
    )
    row = cur.fetchone()
    return row[0] if row else None


def begin_critique_session(note_id, note_type, content):
    """
    Creates a critique session and gets the critic's first turn. Shared
    between start() below (an existing draft moving into review) and
    notes.new() (a brand new note going straight into review, skipping the
    old separate draft stop). Assumes notes.status is already 'under_review'
    -- the caller is responsible for that.
    """
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO critique_sessions (note_id) VALUES (%s) RETURNING id",
                (str(note_id),),
            )
            session_id = cur.fetchone()[0]

    # Connection closed above -- now the slow part, no connection held open.
    result = get_critic_reply(note_type, content, transcript=[], turn_number=1, turn_cap=TURN_CAP)
    reply_text = result["reply"]
    inp_tokens = result["input_tokens"]
    out_tokens = result["output_tokens"]

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO critique_turns (session_id, turn_number, role, content) "
                "VALUES (%s, 1, 'critic', %s)",
                (str(session_id), reply_text),
            )
            # Save initial token usage to the session
            cur.execute(
                "UPDATE critique_sessions SET critic_input_tokens = %s, critic_output_tokens = %s WHERE id = %s",
                (inp_tokens, out_tokens, str(session_id)),
            )


@review_bp.route("/<uuid:note_id>/review/start", methods=["POST"])
@require_login
def start(note_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE notes SET status = 'under_review' WHERE id = %s "
                "RETURNING note_type, content",
                (str(note_id),),
            )
            row = cur.fetchone()
            if row is None:
                abort(404)
            note_type, content = row

    begin_critique_session(note_id, note_type, content)

    return redirect(url_for("review.view", note_id=note_id))


@review_bp.route("/<uuid:note_id>/review")
@require_login
def view(note_id):
    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT note_type, content, status FROM notes WHERE id = %s",
                (str(note_id),),
            )
            note = cur.fetchone()
            if note is None:
                abort(404)
            note_type, content, status = note

            session_id = _open_session_id(cur, note_id)
            turns = []
            if session_id:
                cur.execute(
                    "SELECT role, content FROM critique_turns "
                    "WHERE session_id = %s ORDER BY turn_number",
                    (str(session_id),),
                )
                turns = cur.fetchall()

    if session_id is None:
        return f"<p>{content}</p><p>Status: {status} -- no open review for this note.</p>"

    transcript_html = "".join(f"<p><b>{role}:</b> {text}</p>" for role, text in turns)

    return f"""
        <p><a href="/notes/{note_id}">&larr; back</a></p>
        <p style="font-size: 0.85em; color: #666;">Classified as: {note_type}</p>

        <form method="post" id="finalize-form"></form>
        <textarea id="note-content" name="content" form="finalize-form" rows="4" cols="50" readonly>{content}</textarea><br>
        <button type="button" onclick="document.getElementById('note-content').readOnly = false; document.getElementById('note-content').focus();">Edit</button>
        <button type="submit" form="finalize-form" formaction="/notes/{note_id}/review/approve">Save</button>
        <form method="post" action="/notes/{note_id}/delete" style="display: inline;">
            <button type="submit">Cancel</button>
        </form>
        <p style="font-size: 0.85em; color: #666;">Click Edit to change the wording. Save stores whatever's currently shown above. Cancel deletes this note entirely.</p>

        {transcript_html}

        <form method="post" action="/notes/{note_id}/review/reply">
            <textarea name="reply" rows="4" cols="50" placeholder="Reply to the critic..."></textarea><br>
            <button type="submit">Send</button>
        </form>
    """


@review_bp.route("/<uuid:note_id>/review/reply", methods=["POST"])
@require_login
def reply(note_id):
    user_reply = request.form.get("reply", "").strip()
    if not user_reply:
        abort(400)

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT note_type, content FROM notes WHERE id = %s", (str(note_id),))
            note = cur.fetchone()
            if note is None:
                abort(404)
            note_type, content = note

            session_id = _open_session_id(cur, note_id)
            if session_id is None:
                abort(400)  # nothing open to reply to

            cur.execute(
                "SELECT role, content, turn_number FROM critique_turns "
                "WHERE session_id = %s ORDER BY turn_number",
                (str(session_id),),
            )
            rows = cur.fetchall()

    transcript = [
        {"role": "assistant" if role == "critic" else "user", "content": text}
        for role, text, _ in rows
    ]
    next_turn_number = rows[-1][2] + 1 if rows else 1
    # Turn cap counts critic replies specifically, not every message -- this
    # reply will be the Nth time the critic has pushed back.
    critic_turn_number = sum(1 for role, _, _ in rows if role == "critic") + 1

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO critique_turns (session_id, turn_number, role, content) "
                "VALUES (%s, %s, 'user', %s)",
                (str(session_id), next_turn_number, user_reply),
            )

    transcript.append({"role": "user", "content": user_reply})
    result = get_critic_reply(
        note_type, content, transcript, turn_number=critic_turn_number, turn_cap=TURN_CAP
    )
    
    critic_reply_text = result["reply"]
    inp_tokens = result["input_tokens"]
    out_tokens = result["output_tokens"]

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO critique_turns (session_id, turn_number, role, content) "
                "VALUES (%s, %s, 'critic', %s)",
                (str(session_id), next_turn_number + 1, critic_reply_text),
            )
            # Accumulate token usage for the session
            cur.execute(
                "UPDATE critique_sessions SET critic_input_tokens = critic_input_tokens + %s, critic_output_tokens = critic_output_tokens + %s WHERE id = %s",
                (inp_tokens, out_tokens, str(session_id)),
            )

    return redirect(url_for("review.view", note_id=note_id))


@review_bp.route("/<uuid:note_id>/review/approve", methods=["POST"])
@require_login
def approve(note_id):
    edited_content = request.form.get("content", "").strip()
    if not edited_content:
        abort(400)

    with get_user_scoped_connection(session["user_id"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content FROM notes WHERE id = %s", (str(note_id),))
            existing = cur.fetchone()
            if existing is None:
                abort(404)
            original_content = existing[0]

            # Same versioning principle as a merge -- if the note's wording
            # changed during review, preserve what it originally said rather
            # than silently overwrite it.
            if edited_content != original_content:
                cur.execute(
                    "SELECT COALESCE(MAX(version_number), 0) FROM note_versions WHERE note_id = %s",
                    (str(note_id),),
                )
                next_version = cur.fetchone()[0] + 1
                cur.execute(
                    "INSERT INTO note_versions (note_id, version_number, content) VALUES (%s, %s, %s)",
                    (str(note_id), next_version, original_content),
                )

            cur.execute(
                "UPDATE critique_sessions SET resolution = 'approved', ended_at = now() "
                "WHERE note_id = %s AND resolution IS NULL",
                (str(note_id),),
            )
            cur.execute(
                "UPDATE notes SET content = %s, status = 'approved' WHERE id = %s RETURNING content",
                (edited_content, str(note_id)),
            )
            row = cur.fetchone()

    if row:
        embedding = embed_and_store(note_id, row[0])
        run_integration(note_id, row[0], embedding)

    return redirect(url_for("notes.view", note_id=note_id))