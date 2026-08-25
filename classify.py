"""
Classifies a note into claim / reflection / question.
Now returns a dict with the type AND the token usage.
"""

import os
from anthropic import Anthropic

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_MODEL = "claude-haiku-4-5-20251001"
_VALID_TYPES = {"claim", "reflection", "question"}

_SYSTEM_PROMPT = """Classify the following personal note into exactly one category:
- claim: an assertion presented as true or false.
- reflection: personal processing of an experience, observation, or feeling.
- question: something the user wants to explore or find an answer to later.
Respond with ONLY one word, no punctuation, no explanation: claim, reflection, or question."""

def classify_note(content):
    response = _client.messages.create(
        model=_MODEL,
        max_tokens=10,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    
    usage = response.usage
    inp = usage.input_tokens if usage else 0
    out = usage.output_tokens if usage else 0

    raw = response.content[0].text.strip().lower()
    note_type = raw if raw in _VALID_TYPES else "reflection"

    return {"type": note_type, "input_tokens": inp, "output_tokens": out}