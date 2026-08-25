"""
Computes note embeddings via a local Ollama server. See README.md section 9
for why local: no API key, no per-token cost, fits a personal, local-first
project. Ollama only needs to be running at the moment a note is approved --
nothing here requires it running continuously.
"""

import requests

_OLLAMA_URL = "http://localhost:11434/api/embed"
_MODEL = "nomic-embed-text"


def get_embedding(text):
    """Returns a single embedding vector (list of 768 floats) for the given text."""
    response = requests.post(_OLLAMA_URL, json={"model": _MODEL, "input": text}, timeout=30)
    response.raise_for_status()
    return response.json()["embeddings"][0]