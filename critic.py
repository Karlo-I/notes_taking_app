"""
The critic -- adversarial pass.
Now returns a dict with the reply text AND the token usage.
"""

import os
from anthropic import Anthropic

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_MODEL = "claude-haiku-4-5-20251001"

_PERSONA = """You are a rigorous thinking partner reviewing a personal note before it enters the user's permanent knowledge base.
Your goal is to strengthen the user's reasoning, not to enforce mainstream consensus or debate their personal values.
- Evaluate the internal logic and stated evidence of the note.
- If a claim is contrarian or challenges official narratives, DO NOT dismiss it as a "conspiracy theory." Instead, ask what specific evidence supports it.
- Respect that this is the user's personal knowledge base. They have the final say on their beliefs.
- Keep your response concise (under 150 words). Get straight to the point."""

_DIMENSIONS = {
    "claim": """This note makes a claim. Check for:
- Internal logical consistency and unstated assumptions.
- Whether the user has provided or cited specific evidence for unconventional claims.
- Alternative explanations, but frame them as questions for the user to consider, not as debunking.
- Allow the user to hold contrarian views if they can articulate their reasoning.""",
    
    "reflection": """This note is a personal belief, value, or reflection. 
- DO NOT fact-check, debate, or challenge the validity of the belief itself. 
- Only ask clarifying questions that help the user deepen their own thinking (e.g., "What specific experience led you to this conclusion?" or "How does this align with your other notes on X?").""",
    
    "question": """This note is an open question. Check:
- Whether it's specific enough to be answerable.
- If it's already answered in the <existing_notes>, point to it and suggest a narrower, more precise follow-up question."""
}

_CONTEXT_GUIDANCE = {
"claim": "Check whether this claim conflicts with any of the notes in the <existing_notes> block.",
"reflection": "Use the <existing_notes> block to ask a sharper, more specific question grounded in what was actually written before.",
"question": "If one of the notes in <existing_notes> already answers the question, point to it and ask whether a narrower question is actually what's needed.",
}

_ANTI_CAPITULATION = """Do not soften or withdraw a prior objection just because the user pushed back. Only concede a specific point if their reply directly addresses the gap you named."""

def _truncate_text(text: str, max_words: int = 75) -> str:
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return text

def build_system_prompt(note_type: str, turn_number: int, turn_cap: int) -> str:
    parts = [_PERSONA, _DIMENSIONS[note_type], _CONTEXT_GUIDANCE[note_type], _ANTI_CAPITULATION]
    if turn_number >= turn_cap:
        parts.append('This is the final turn. State your strongest remaining objection plainly, then explicitly hand control back to the user. Do not continue arguing past this turn.')
    return "\n\n".join(parts)

def get_critic_reply(note_type, note_content, transcript, turn_number, turn_cap, related_notes=None):
    system = build_system_prompt(note_type, turn_number, turn_cap)
    user_content_parts = []
    if related_notes:
        truncated = [_truncate_text(n) for n in related_notes]
        joined = "\n".join(f"- {n}" for n in truncated)
        user_content_parts.append(f"<existing_notes>\n{joined}\n</existing_notes>")
    user_content_parts.append(f"<note_to_review>\n{note_content}\n</note_to_review>")

    messages = [{"role": "user", "content": "\n\n".join(user_content_parts)}]
    messages.extend(transcript)

    response = _client.messages.create(
        model=_MODEL,
        max_tokens=400,
        system=system,
        messages=messages,
    )
    usage = response.usage
    return {
        "reply": response.content[0].text,
        "input_tokens": usage.input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0
    }