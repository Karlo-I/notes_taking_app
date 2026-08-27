#!/bin/bash
cd "/Users/karloigloria/Documents/CS50 AI/Notes_Taking Project"

# 1. Start the database container
echo "🐳 Starting database..."
docker-compose up -d

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Start the Flask app
nohup python wsgi.py > app.log 2>&1 &
echo "✅ App started! Visit http://127.0.0.1:5000"
