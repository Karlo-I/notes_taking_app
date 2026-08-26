#!/bin/bash

# Exit immediately if a command fails
set -e

echo "🚀 Starting Notes Taking App..."

# 1. Activate the virtual environment (adjust 'venv' if yours is named differently)
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ Virtual environment not found. Please create one or adjust the script."
    exit 1
fi

# 2. Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found. The app may fail to start."
fi

# 3. Run the application
# Using python wsgi.py (or gunicorn if you prefer production serving)
echo "✅ Environment loaded. Starting server on http://127.0.0.1:5000"
python wsgi.py