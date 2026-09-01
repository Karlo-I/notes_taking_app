# Design Reference — Notes → Critic → Knowledge Base → Output

**Purpose of this document:** single source of truth for architecture decisions made during planning. Paste this into any AI session (Claude Code, another tool, a fresh chat) before asking for implementation help — it carries context that a fresh chat won't have.

**AI assistance disclosure:** This document and the planning behind it were developed in conversation with Claude (Anthropic). All architectural decisions, trade-off calls, and scope choices are the author's own, made deliberately across a design conversation — not defaults accepted from the AI.

**Last updated:** August 28, 2026

---

## 1. Thesis

A personal note-taking and reflection tool with one core mechanic: an adversarial AI critic sits between a raw note and the permanent knowledge base, and nothing enters storage until the user has either satisfied the critique or explicitly overridden it with a reason. The AI's role is to sharpen thinking before it's recorded, not to record thinking uncritically. Output generation (Q&A doc, narration script, Socratic dialogue) draws on the resulting knowledge base but does not carry its own critique cycle — that friction lives only at the point of capture.

## 2. System architecture — two pipelines

**Note ingestion:**
Raw note → critic dialogue (bounces with user until approved or overridden) → integration agent (merge / link / new) → knowledge database

**Output generation:**
Topic or question → topic identification (LLM maps query to existing KB topics) → filtered vector search (strictly within matched topics) → LLM re-ranking (filters noise, ranks top 8 snippets) → draft generation → final output (screen or PDF)

No critique cycle on the output side — deliberately dropped to cut cost and complexity in half; the note-ingestion critic is where the real value is.

## 3. Critic dialogue design

**Note types and posture:**

| Type | Posture | Checks |
|---|---|---|
| Claim / argument | Adversarial | Unstated assumptions, alternative explanations, overgeneralization, contradiction with existing notes |
| Reflection / observation | Socratic, not adversarial | What triggered it, one-off vs. pattern, what would change your mind |
| Open question | Light touch | Is it genuinely open (not already answered in the KB), is it specific enough to be answerable |

**Prompt layers (structurally separate, tuned independently):**
1. Persona/tone — direct, no diplomatic hedging
2. Mode-conditional dimensions — swappable block per note_type
3. Context injection (claim-type only) — one retrieval pass against existing notes at session start, cached for the session, checked for contradiction
4. Anti-capitulation clause — do not soften a critique unless the user's reply addresses the specific named gap
5. Turn-aware behavior — below cap, argue normally; at cap, state the strongest remaining objection and explicitly hand control back to the user

**Escape hatch:** user can override at any point with a required one-line reason. Resolution stored as `approved_clean` / `approved_overridden` / `abandoned`. This preserves user sovereignty — the critic informs, the user decides.

**Critic reply format:** free text, not structured JSON. Scaffolding (mode, context, turn count) is structured; the critique's voice stays natural.

## 4. Integration agent

Three-way decision, not binary: **merge** into an existing note, **link** as related-but-distinct, or **new**. Runs once per approved note: embed → vector search existing notes → LLM decides among the three given candidates.

Merges are append-only — a new `note_versions` row is written, nothing is overwritten in place. This preserves an audit trail and avoids silent loss of the user's original thought.

## 5. Data model

| Table | Key fields | Purpose |
|---|---|---|
| `critique_sessions` | id, note_id, resolution, override_reason | One row per critique dialogue |
| `critique_turns` | id, session_id, turn_number, role, content | The dialogue transcript |
| `notes` | id, user_id, note_type, content, embedding, status | Current state; embedding written only after approval |
| `note_versions` | id, note_id, version_number, content | Append-only merge history |
| `note_links` | id, note_id, related_note_id, link_type | Related-but-distinct notes — the graph structure |
| `note_topics` | note_id, topic_id | Junction table linking notes to their umbrella topics (M:M). |
| `outputs` | id, user_id, output_type, topic_query, generated_content | One table for all three output types |
| `output_sources` | id, output_id, note_id | Provenance — which notes grounded which output |
| `topics` | id, user_id, name | High-level umbrella concepts extracted from notes (e.g., "US Withholding Tax"). |
| `users` | id, oauth_provider, oauth_subject_id, display_name | Identity via OAuth only — no password field |

Relationships: users→notes (1:M), notes→note_versions (1:M), notes→critique_sessions→critique_turns (1:M nested), notes↔notes via note_links (self-referencing M:M), notes↔topics via note_topics (M:M), users→outputs (1:M), outputs↔notes via output_sources (M:M).

## 6. Security

- **Transport:** HTTPS, automatic via hosting provider. No engineering cost.
- **At rest:** provider-level disk encryption (default from hosting provider) is the chosen baseline. Field-level or zero-knowledge encryption was considered and explicitly not adopted — it conflicts with the core feature, since the LLM needs plaintext at request time to critique and retrieve.
- **Auth:** OAuth (Google/GitHub). No password ever touches the app. Callback URLs strictly use `127.0.0.1` (not `localhost`) to prevent redirect_uri mismatch errors.
- **Row Level Security:** enabled on all user-scoped tables. Policies check `user_id = current_setting('app.current_user_id')`. **Must be set per-request via `SET LOCAL` inside a transaction, not per-connection** — pooled connections reused across users will leak context otherwise if this is done wrong. This is the single most important implementation detail to get right early.
- **Cache Prevention:** Strict HTTP headers (`Cache-Control`, `Pragma`, `Expires`) are applied to all HTML responses via an `@app.after_request` hook. This prevents the browser from caching protected pages, ensuring that hitting the "Back" button after logout forces a server check and redirects to the login page, rather than showing a cached version of private data.
- **AI training:** whichever LLM provider is used, confirm current terms directly rather than assume — state findings honestly in the app's own privacy page.

## 7. Cost model

Per note: 1 embedding call (near-free) + N critic turns (bounded by user, not by the system) + 1 integration-agent call.
Per output: 1 embedding (query) + 1 topic-identification call (Haiku) + 1 re-ranking call (Haiku) + 1 draft-generation call. No critique call on this side.
Model choice: Haiku-class model for critic and integration agent (structured, bounded tasks); a stronger model only where prose quality in the final draft output matters more.

## 8. Build order

1. Schema + migrations
2. Auth (OAuth) + RLS policies from the start, not retrofitted
3. Notes CRUD without the critic — prove the basic write path
4. Critic dialogue loop
5. Integration agent
6. Retrieval + output generation (all three output types share this infrastructure)
7. PDF export
8. Background run script (start.sh) & Docker auto-start configuration
9. UI/UX Overhaul (Sidebar layout, Jinja2 templates, premium CSS)
10. Glassmorphism Modal system (replacing separate detail pages)
11. Global hybrid search (keyword + vector) in the navbar
12. Mobile-responsive CSS tweaks

## 9. Tech stack

- Backend: Python / Flask (Blueprints & App Factory pattern)
- DB: PostgreSQL + pgvector, run locally via Docker — same engine in dev and prod, no dual-schema translation layer needed
- Auth: OAuth 2.0 (Google/GitHub) via Authlib
- AI: Claude Haiku-class model for critic + integration; stronger model optional for draft prose
- Frontend: Jinja2 Templates (base inheritance), Vanilla JavaScript (Fetch API for modals), CSS3 (CSS variables, Glassmorphism `backdrop-filter`)
- DevOps: Custom `start.sh` background script, Docker Compose for local PostgreSQL

## 10. What this deliberately is not

Not built for scale or multi-tenant SaaS — built for one user's personal reflection practice, prioritizing coherence and cost-efficiency over throughput. Not a general PKM tool — the critic-on-ingestion gate is the entire point, not a bolt-on feature.

## 11. Not yet decided

- Exact embedding model and vector dimension size
- Whether `users` table needs its own RLS policy, given the OAuth login lookup happens before a user context exists (open chicken-and-egg problem, addressed with a narrower app-level query pattern for login only — see comment in schema.sql)

## 12. Implementation Notes & Recent Additions

- Modals & JSON: The `notes.py` and `outputs.py` detail routes return raw JSON when queried with `?format=json`. This powers the frontend modal system without requiring a separate API blueprint.
- Embeddings: Notes are only embedded into the vector database `after` they are approved. Drafts and notes under review are never searchable.
- Versioning: When a note is merged or its wording is changed during the review process, the original content is preserved in the `note_versions` table. Nothing is ever permanently lost.
- Docker & Background Processes: The app and database are decoupled. `start.sh` handles spinning up Docker and the Flask app in the background. Docker Desktop is configured to auto-start on Mac login.
- Advanced Retrieval Pipeline: Output generation uses a 3-stage retrieval process: 1. LLM identifies relevant `topics` from the query, 2. Vector search is strictly filtered to those topics (ensuring umbrella concepts like "Chapter 3" are found even if the query only says "871m"), 3. LLM re-ranking filters out noisy snippets before the final generation.
- Topic Extraction: Runs automatically in `review.py` after a note is approved. Uses a cheap Haiku call to extract 1-3 broad topics and links them in the `note_topics` table.
- Re-ranking: Uses a cheap Haiku call to read the first 250 characters of up to 12 retrieved notes, returning only the top 8 most relevant indices to save context window space and prevent hallucination.

## 13. Potential Future Adjustments to the Set Parameters

1. The Snippet Size (Currently 250 characters)

- What it does: It chops off the beginning of the note to show the re-ranker.
- When to change it: If you stop writing "atomic notes" (short, single-concept thoughts) and start writing long-form essays (1,000+ words).
- The Risk: If you write a 2-page note, the core insight might be in paragraph 4. A 250-character snippet (about 50 words) will only show the introduction, and the re-ranker might incorrectly drop a highly valuable note because it didn't see the "good part."
- The Fix: Increase to 500 or 1000 characters. Trade-off: This will slightly increase the cost of the re-ranking step.

2. The Candidate Pool (Currently 12 notes)

- What it does: It tells the vector search to grab the top 12 closest notes before the re-ranker looks at them.
- When to change it: When your knowledge base grows past 500–1,000 notes.
- The Risk: "Tunnel Vision." If you have 50 notes on "US Tax" and 50 notes on "Career," and you ask a broad question, the top 12 results might all be from the Tax category, completely blocking the Career notes from even being seen by the re-ranker.
- The Fix: Increase the RETRIEVAL_LIMIT to 20 or 25. Trade-off: The re-ranker prompt gets larger and costs a few cents more per query.

3. The Final Limit (Currently 8 notes)

- What it does: It restricts the final, expensive Output LLM to only seeing the top 8 notes.
- When to change it: Almost never, unless you upgrade your Output Model.
- The Risk: "Lost in the Middle." Current LLMs (even Sonnet/Opus) suffer from attention degradation. If you feed them 20 notes, they will hallucinate or ignore the middle 12. 8 notes (roughly 3,000–4,000 words) is the "Goldilocks" zone for high-quality synthesis.
- The Fix: Only increase this if you switch to a model with a massive context window (e.g., 200k tokens) and you specifically want to generate a "Deep Dive Literature Review" rather than a standard summary.

4. The Similarity Threshold (Currently 0.20)

- What it does: The minimum similarity score required for a note to be considered.
- When to change it: As your database grows significantly.
- The Risk: "Noise Floor." Right now, 0.20 is very loose, which is great for finding everything. But when you have 1,000 notes, a 0.20 threshold will pull in hundreds of completely irrelevant notes, crashing your re-ranker or blowing up your token costs.
- The Fix: You will likely need to tighten this to 0.35 or 0.45 as your DB grows. Because your Topic Filtering (Phase 4) is now doing the heavy lifting for broad recall, you can afford to make the raw vector search stricter.