"""
Computes note embeddings via Jina AI API.
Uses built-in urllib to ensure reliability within the Flask environment.
"""
import os
import urllib.request
import json

_JINA_URL = "https://api.jina.ai/v1/embeddings"
_MODEL = "jina-embeddings-v3"

def get_embedding(text):
    api_key = os.getenv('JINA_API_KEY')
    if not api_key:
        raise ValueError("JINA_API_KEY not found in environment variables.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": _MODEL,
        "task": "retrieval.passage",
        "normalized": True,
        "input": [text]
    }
    
    req_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(_JINA_URL, data=req_data, headers=headers, method='POST')
    
    with urllib.request.urlopen(req, timeout=30) as response:
        response_body = response.read().decode('utf-8')
        result = json.loads(response_body)
        return result["data"][0]["embedding"]