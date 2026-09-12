import os
import psycopg2
from embeddings import get_embedding
from db import vector_literal

# Connect directly to the database
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print(" Searching for approved notes with missing embeddings...")

# Find all approved notes where embedding is NULL
cur.execute("""
    SELECT id, content FROM notes 
    WHERE status = 'approved' AND embedding IS NULL
""")
notes_to_fix = cur.fetchall()

print(f"Found {len(notes_to_fix)} notes to fix.\n")

for note_id, content in notes_to_fix:
    print(f"⚡ Processing note {note_id[:8]}...")
    try:
        # Generate the embedding vector
        vector = get_embedding(content)
        
        # Update the database
        literal = vector_literal(vector)
        cur.execute("UPDATE notes SET embedding = %s::vector WHERE id = %s", (literal, str(note_id)))
        conn.commit()
        print("✅ Success")
        
    except Exception as e:
        print(f" Failed: {e}")
        conn.rollback()

print("\n🎉 Done! All missing embeddings have been generated.")
cur.close()
conn.close()