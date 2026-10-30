import os
import uuid
import torch
import yt_dlp
from datetime import datetime
from flask import Blueprint, request, render_template, session, jsonify
from werkzeug.utils import secure_filename
from db import get_user_scoped_connection
from decorators import require_login

transcribe_bp = Blueprint("transcribe", __name__, url_prefix="/transcribe")

# --- LAZY LOADING: Prevents Render from crashing on startup ---
_transcribe_model = None

def get_transcription_model():
    global _transcribe_model
    if _transcribe_model is None:
        import whisper
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        print(f"Loading Whisper model on {device.upper()}...")
        
        # Use 'tiny' on Render (CPU) to stay under the 512MB RAM limit.
        # Use 'base' locally on your Mac (MPS) for better accuracy/speed.
        model_size = "tiny" if device == "cpu" else "base"
        print(f"Using '{model_size}' model to optimize memory.")
        
        _transcribe_model = whisper.load_model(model_size, device=device)
        print("Model loaded! Ready to transcribe.")
    return _transcribe_model

UPLOAD_FOLDER = 'temp_uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DOWNLOAD_FOLDER = os.path.join('static', 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@transcribe_bp.route("/")
@require_login
def index():
    return render_template("transcribe/index.html")

@transcribe_bp.route("/process", methods=["POST"])
@require_login
def process_transcription():
    print("=== TRANSCRIPTION STARTED ===")
    
    youtube_url = request.form.get('youtube_url', '').strip()
    
    # --- FIX 1: Clean the URL to remove playlist parameters ---
    if youtube_url and '&list=' in youtube_url:
        youtube_url = youtube_url.split('&list=')[0]
        print(f"Cleaned URL (removed playlist): {youtube_url}")
    # ----------------------------------------------------------
    
    file = request.files.get('audio_file')
    
    # --- FIX 2: File size check to prevent Render OOM crashes ---
    if file and file.filename != '':
        file.seek(0, 2)  # Seek to end of file
        file_length = file.tell()
        file.seek(0)     # Reset to beginning so it can be saved
        
        # Limit to 15MB on Render (512MB RAM limit)
        max_file_size = 15 * 1024 * 1024  # 15MB
        
        if file_length > max_file_size:
            size_mb = file_length // 1024 // 1024
            return jsonify({
                "success": False, 
                "error": f"File too large for cloud processing ({size_mb}MB). Please use files under 15MB or run locally."
            }), 400
    # -------------------------------------------------------------
    
    temp_filepath = os.path.join(UPLOAD_FOLDER, f"temp_{uuid.uuid4()}")
    actual_audio_path = None

    try:
        # 1. Determine the source of the audio
        if youtube_url:
            print(f"Downloading from YouTube: {youtube_url}")
            import glob
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_filepath + '.%(ext)s',
                'no_warnings': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
            downloaded_files = glob.glob(temp_filepath + '.*')
            if downloaded_files:
                actual_audio_path = downloaded_files[0]
                print(f"Downloaded to: {actual_audio_path}")
            else:
                print("ERROR: No files found after download")
                return jsonify({"success": False, "error": "Download failed - no files found"}), 400
                
        elif file and file.filename != '':
            print(f"Uploading file: {file.filename}")
            actual_audio_path = f"{temp_filepath}_{secure_filename(file.filename)}"
            file.save(actual_audio_path)
            print(f"Saved to: {actual_audio_path}")

        else:
            print("ERROR: No file or URL provided")
            return jsonify({"success": False, "error": "Please provide a URL or file."}), 400

        # 2. Transcribe (LAZY LOADED)
        print("Starting transcription...")
        model = get_transcription_model()
        result = model.transcribe(actual_audio_path, verbose=False) 
        print(f"Transcription complete. Segments: {len(result['segments'])}")

        # 3. Format transcript
        transcript_lines = []
        for segment in result["segments"]:
            start_time = format_timestamp(segment["start"])
            text = segment["text"].strip()
            transcript_lines.append(f"[{start_time}] {text}")
        
        full_transcript = "\n\n".join(transcript_lines)
        print(f"Transcript length: {len(full_transcript)} chars")
        
        # Generate source name
        if youtube_url:
            source_name = "YouTube Video"
        else:
            source_name = os.path.splitext(secure_filename(file.filename))[0]
            if len(source_name) > 30:
                source_name = source_name[:30] + "..."
        
        timestamp = datetime.now().strftime("%I:%M %p")

        # 4. Save file to static folder
        unique_filename = f"{uuid.uuid4()}.txt"
        final_save_path = os.path.join(DOWNLOAD_FOLDER, unique_filename)
        with open(final_save_path, "w", encoding="utf-8") as f:
            f.write(full_transcript)
        print(f"Saved transcript to: {final_save_path}")

        # 5. Save as a Note in the Database
        note_id = None
        user_id = session["user_id"]
        print(f"Saving to database for user: {user_id}")
        
        try:
            with get_user_scoped_connection(user_id) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO notes (user_id, note_type, content, status) 
                        VALUES (%s, %s, %s, %s) RETURNING id
                        """,
                        (user_id, 'claim', full_transcript, 'under_review')
                    )
                    result = cur.fetchone()
                    if result:
                        note_id = result[0]
                        print(f"Note saved with ID: {note_id}")
                conn.commit()
        except Exception as db_error:
            print(f"DATABASE ERROR: {str(db_error)}")

        # 6. Return JSON
        response_data = {
            "success": True,
            "source_name": source_name,
            "timestamp": timestamp,
            "download_url": f"/static/downloads/{unique_filename}",
            "notes_url": "/notes/",
            "note_id": note_id
        }
        print(f"Returning success: {response_data}")
        return jsonify(response_data)

    except Exception as e:
        error_msg = str(e)
        
        # Check if the error is the known Instagram/YouTube datacenter block
        if "403: Forbidden" in error_msg or "Failed to extract any player response" in error_msg:
            friendly_error = (
                "Cloud servers are currently blocked by this platform (Instagram/YouTube). "
                "Please either: 1) Upload the MP3 file directly, or 2) Use the local desktop app for URL downloads."
            )
            print(f"BLOCKED BY PLATFORM: {friendly_error}")
            return jsonify({"success": False, "error": friendly_error}), 400
        else:
            # For any other error, show the standard message
            print(f"Transcription error: {error_msg}")
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "error": f"Transcription error: {error_msg}"}), 500
    
    finally:
        if actual_audio_path and os.path.exists(actual_audio_path):
            try: 
                os.remove(actual_audio_path)
                print(f"Cleaned up: {actual_audio_path}")
            except Exception as e:
                print(f"Cleanup error: {e}")

# --- Route to delete a note ---
@transcribe_bp.route("/delete_note/<note_id>", methods=["POST"])
@require_login
def delete_note(note_id):
    user_id = session["user_id"]
    try:
        with get_user_scoped_connection(user_id) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM notes WHERE id = %s AND user_id = %s", (note_id, user_id))
            conn.commit()
        print(f"Deleted note {note_id}")
        return jsonify({"success": True})
    except Exception as e:
        print(f"Delete error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"