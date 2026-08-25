# Design Reference — Notes → Critic → Knowledge Base → Output

**Purpose of this document:** single source of truth for architecture decisions made during planning. Paste this into any AI session (Claude Code, another tool, a fresh chat) before asking for implementation help — it carries context that a fresh chat won't have.

**AI assistance disclosure:** This document and the planning behind it were developed in conversation with Claude (Anthropic). All architectural decisions, trade-off calls, and scope choices are the author's own, made deliberately across a design conversation — not defaults accepted from the AI.

**Last updated:** placeholder — update as decisions change.

---

## 1. Thesis

A personal note-taking and reflection tool with one core mechanic: an adversarial AI critic sits between a raw note and the permanent knowledge base, and nothing enters storage until the user has either satisfied the critique or explicitly overridden it with a reason. The AI's role is to sharpen thinking before it's recorded, not to record thinking uncritically. Output generation (Q&A doc, narration script, Socratic dialogue) draws on the resulting knowledge base but does not carry its own critique cycle — that friction lives only at the point of capture.

## 2. System architecture — two pipelines

**Note ingestion:**
Raw note → critic dialogue (bounces with user until approved or overridden) → integration agent (merge / link / new) → knowledge database

**Output generation:**
Topic or question → draft generation (retrieval + LLM writes) → final output (screen or PDF)

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
| `users` | id, oauth_provider, oauth_subject_id, display_name | Identity via OAuth only — no password field |
| `notes` | id, user_id, note_type, content, embedding, status | Current state; embedding written only after approval |
| `note_versions` | id, note_id, version_number, content | Append-only merge history |
| `critique_sessions` | id, note_id, resolution, override_reason | One row per critique dialogue |
| `critique_turns` | id, session_id, turn_number, role, content | The dialogue transcript |
| `note_links` | id, note_id, related_note_id, link_type | Related-but-distinct notes — the graph structure |
| `outputs` | id, user_id, output_type, topic_query, generated_content | One table for all three output types |
| `output_sources` | id, output_id, note_id | Provenance — which notes grounded which output |

Relationships: users→notes (1:M), notes→note_versions (1:M), notes→critique_sessions→critique_turns (1:M nested), notes↔notes via note_links (self-referencing M:M), users→outputs (1:M), outputs↔notes via output_sources (M:M).

## 6. Security

- **Transport:** HTTPS, automatic via hosting provider. No engineering cost.
- **At rest:** provider-level disk encryption (default from hosting provider) is the chosen baseline. Field-level or zero-knowledge encryption was considered and explicitly not adopted — it conflicts with the core feature, since the LLM needs plaintext at request time to critique and retrieve.
- **Auth:** OAuth (Google/GitHub). No password ever touches the app.
- **Row Level Security:** enabled on all user-scoped tables. Policies check `user_id = current_setting('app.current_user_id')`. **Must be set per-request via `SET LOCAL` inside a transaction, not per-connection** — pooled connections reused across users will leak context otherwise if this is done wrong. This is the single most important implementation detail to get right early.
- **AI training:** whichever LLM provider is used, confirm current terms directly rather than assume — state findings honestly in the app's own privacy page.

## 7. Cost model

Per note: 1 embedding call (near-free) + N critic turns (bounded by user, not by the system) + 1 integration-agent call.
Per output: 1 embedding (query) + 1 draft-generation call. No critique call on this side.
Model choice: Haiku-class model for critic and integration agent (structured, bounded tasks); a stronger model only where prose quality in the final draft output matters more.

## 8. Build order

1. Schema + migrations
2. Auth (OAuth) + RLS policies from the start, not retrofitted
3. Notes CRUD without the critic — prove the basic write path
4. Critic dialogue loop
5. Integration agent
6. Retrieval + output generation (all three output types share this infrastructure)
7. PDF export

## 9. Tech stack

- Backend: Python / Flask
- DB: PostgreSQL + pgvector, run locally via Docker — same engine in dev and prod, no dual-schema translation layer needed
- Auth: OAuth 2.0 (Google/GitHub)
- AI: Claude Haiku-class model for critic + integration; stronger model optional for draft prose
- PDF: not yet chosen (see open questions)

## 10. What this deliberately is not

Not built for scale or multi-tenant SaaS — built for one user's personal reflection practice, prioritizing coherence and cost-efficiency over throughput. Not a general PKM tool — the critic-on-ingestion gate is the entire point, not a bolt-on feature.

## 11. Not yet decided

- PDF generation library
- Exact embedding model and vector dimension size
- Whether `users` table needs its own RLS policy, given the OAuth login lookup happens before a user context exists (open chicken-and-egg problem, addressed with a narrower app-level query pattern for login only — see comment in schema.sql)
