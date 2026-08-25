"""
The integration agent -- decides how a newly approved note relates to existing notes.
Now includes token usage in the returned dict.
"""

import json
import os
from anthropic import Anthropic

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """You decide how a newly approved note relates to notes already in the user's knowledge base.
Choose exactly one:
- "merge": the new note says essentially the same thing as one candidate. Write the combined content.
- "link": the new note and a candidate share an underlying subject but make distinct claims.
- "new": the candidates address a different subject entirely.
Respond with ONLY a JSON object, no other text, no markdown fences:
{"decision": "merge" | "link" | "new", "target_note_id": "<uuid or null>", "merged_content": "<string or null>"}
"""

def _strip_code_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()

def decide(note_content, candidates):
    if not candidates:
        return {"decision": "new", "target_note_id": None, "merged_content": None, "input_tokens": 0, "output_tokens": 0}

    candidate_text = "\n\n".join(f'<candidate id="{c["id"]}">\n{c["content"]}\n</candidate>' for c in candidates)
    message = f"<new_note>\n{note_content}\n</new_note>\n\n<candidates>\n{candidate_text}\n</candidates>"

    response = _client.messages.create(
        model=_MODEL,
        max_tokens=800,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    
    usage = response.usage
    inp = usage.input_tokens if usage else 0
    out = usage.output_tokens if usage else 0

    raw = _strip_code_fences(response.content[0].text)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {"decision": "new", "target_note_id": None, "merged_content": None, "input_tokens": inp, "output_tokens": out}

    if result.get("decision") not in ("merge", "link", "new"):
        return {"decision": "new", "target_note_id": None, "merged_content": None, "input_tokens": inp, "output_tokens": out}

    result["input_tokens"] = inp
    result["output_tokens"] = out
    return result