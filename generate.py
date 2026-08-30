"""
Output generation -- retrieval + LLM draft, no critique cycle.

Takes a user_id, topic_query, and output_type; finds relevant approved notes;
constructs a type-specific prompt; calls Anthropic; writes the result to
`outputs` and provenance rows to `output_sources`.

Model choice is configurable via .env (OUTPUT_MODEL) so you can swap
between Haiku and Sonnet/Opus without touching code.
"""

import anthropic
import os
from db import get_user_scoped_connection
from retrieval import find_relevant_notes

_CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_MODEL = os.environ.get("OUTPUT_MODEL", "claude-sonnet-5")


# ---------------------------------------------------------------------------
# Per-type system prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS = {
    "qna": """You are writing a Q&A reference document grounded entirely in the user's personal knowledge base.

RULES:
- Organize the answer by sub-topic with clear headings.
- Cite source note IDs inline using [Note <id>] after any claim drawn from a specific note.
- If the retrieved notes do not cover part of the query, explicitly say "The knowledge base does not address this." Do not speculate.
- Flag contradictions between notes when they exist, noting both sides.
- Be concise and structured. Bullet points and numbered lists are preferred over long paragraphs.
- The user wrote these notes themselves -- treat them as authoritative primary sources, not as external references to be evaluated.
- Do NOT add disclaimers, warnings, or meta-commentary about the sensitivity, controversy, or historical baggage of topics.
- Do NOT mention or reference any notes that were not retrieved as relevant to this query.
- Present the information objectively and neutrally, without judgment or evaluation of the claims' validity.""",

    "narration": """You are writing a narration script intended to be read aloud (audio or video), based on the user's own notes.

RULES:
- Write in short paragraphs with natural spoken cadence. Read it aloud in your head -- if a sentence feels awkward to say, rewrite it.
- Tone: Engaging, conversational, and clear. Use "I" and "we" to make it personal and accessible. The tone should match someone explaining their own insights with confidence.
- Pacing & Phrasing: Keep it moving briskly. Use conversational transitions like "So, here's the thing...", "Now, look at this...", or "This brings us to...". Avoid dense jargon; when a technical term is necessary, define it conversationally on first use.
- Structure: Start with a clear framing of why this topic matters → body that develops the core ideas → conclusion that lands on a memorable takeaway.
- Visual & Pacing Cues: Include practical directions in square brackets for both editing and pacing. E.g., [Zoom in on map], [Show graph], [pause], [emphasis], [slowly].
- Weave in the user's own phrasing, perspectives, and reflections from the retrieved notes naturally. The output should sound like the user explaining their own insights, not a generic textbook or科普 article.
- Do NOT cite note IDs or reference the knowledge base explicitly. This is a polished script, not a research document.
- Present the user's notes objectively and clearly, without adding judgment or evaluation of their validity.""",

    "summary": """You are writing a clean, comprehensive summary of a topic based on the user's personal knowledge base.

RULES:
- Synthesize the retrieved notes into a coherent narrative summary. Do NOT list notes individually or use bullet-point citations.
- Weave together related ideas from multiple notes into unified paragraphs. If notes contradict each other, acknowledge the tension naturally within the prose.
- STRICTLY FORBIDDEN: Do NOT critique the user's notes, suggest counterarguments, demand statistical data, or point out what the user "should" add to make the hypothesis more rigorous. Do not act as an academic peer reviewer.
- Do NOT add a "Limitations" section. Only summarize the information that is actually present in the notes. 
- Use the user's own terminology and framing where possible -- this is a summary of *their* thinking, not an external overview.
- Tone: clear, direct, and complete. No stage directions, no dialogue format, no meta-commentary about the knowledge base itself.
- Length: aim for 300-600 words unless the source material warrants significantly more or less.""",
}

def generate_output(user_id: str, topic_query: str, output_type: str, is_regeneration: bool = False) -> dict:
    """
    Full generation pipeline:
      1. Retrieve relevant approved notes
      2. Build context block from those notes
      3. Call Anthropic with the type-specific system prompt
      4. Persist to outputs + output_sources
      5. Return the output row as a dict

    Returns dict with keys: id, output_type, topic_query, generated_content, created_at
    Raises ValueError if output_type is invalid or no relevant notes found.
    """
    if output_type not in SYSTEM_PROMPTS:
        raise ValueError(f"Unknown output_type: {output_type}. Must be one of {list(SYSTEM_PROMPTS.keys())}")

    # Step 1: retrieve
    relevant_notes = find_relevant_notes(user_id, topic_query)
    if not relevant_notes:
        raise ValueError(
            f"No relevant approved notes found for query: '{topic_query}'. "
            "Try a different topic or add more notes to your knowledge base first."
        )

    # Step 2: build context
    context_lines = []
    for n in relevant_notes:
        context_lines.append(f"[Note {n['id']}] ({n['note_type']}): {n['content']}")
    context_block = "\n\n".join(context_lines)

    system_prompt = SYSTEM_PROMPTS[output_type]
    user_message = (
        f"Topic / question: {topic_query}\n\n"
        f"Relevant notes from the knowledge base:\n{context_block}\n\n"
        f"Write the {output_type} output now."
    )

    if is_regeneration:
        user_message += "\n\n[REGENERATION INSTRUCTION]: This is a request to regenerate a previous output. You MUST provide a fresh perspective. Vary your sentence structure, use different vocabulary, and reorganize the flow. Do not simply repeat the previous output word-for-word."

    # Step 3: call LLM
    response = _CLIENT.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    # Extract text content, handling thinking blocks
    generated_content = ""
    for block in response.content:
        if hasattr(block, 'text'):
            generated_content = block.text
            break
    
    # Fallback if no text block found
    if not generated_content:
        generated_content = str(response.content)

    # Extract token usage from Anthropic response metadata
    usage = response.usage
    input_tokens = usage.input_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0

    # Step 4: persist
    with get_user_scoped_connection(user_id) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO outputs (user_id, output_type, topic_query, generated_content,
                                     input_tokens, output_tokens, model_used)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, output_type, topic_query, generated_content, created_at
                """,
                (user_id, output_type, topic_query, generated_content,
                 input_tokens, output_tokens, _MODEL),
            )
            output_row = cur.fetchone()

            for n in relevant_notes:
                cur.execute(
                    "INSERT INTO output_sources (output_id, note_id) VALUES (%s, %s)",
                    (str(output_row[0]), n["id"]),
                )

    return {
        "id": str(output_row[0]),
        "output_type": output_row[1],
        "topic_query": output_row[2],
        "generated_content": output_row[3],
        "created_at": output_row[4],
    }