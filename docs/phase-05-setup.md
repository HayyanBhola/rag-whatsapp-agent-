# Phase 5 — Agent Routing + Answer Checking

## What this phase adds

Phase 4 showed that a small local model can't be trusted to *choose* facts:
it invented ingredients, mixed up topics and wrote fake dialogues. Phase 5
takes that job away from it.

| Question type | Where the answer comes from | LLM used? |
|---|---|---|
| Price, stock, ingredient list, order status | PostgreSQL, written into a fixed sentence | No |
| Policies, FAQ, product descriptions | Knowledge base → LLM → **answer checker** | Yes, for wording only |
| "Talk to a human", skin reaction, complaint | Fixed reply + `escalate = True` | No |
| "How much is it?" / "Where's my order?" (missing details) | One clarifying question | No |
| "Hi", "thanks" | Fixed reply | No |

New files:
- `agent/router.py` — plain rules that decide the route. Same input gives the same route every time.
- `agent/verifier.py` — checks every LLM answer in code: numbers must exist in the source, no ingredient
  claims that contradict the database, no medical claims, no fake dialogue, most words must come from the
  source. A failed answer is replaced by the source text itself (quoted) or an honest "I don't have that".
- `agent/support_agent.py` — `handle_message()`, the single entry point the chat UI (Phase 6) will call.
- `database/migrations/001_add_ingredients.sql` — adds each product's full ingredient list to PostgreSQL.
- `tests/eval_cases.json` + `tests/run_eval.py` — the automatic test sheet (24 cases).

## Setup (one time)

From the `glowcare-agent` folder:

0. Choose the LLM in your `.env` file (see `.env.example`):
   ```
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-...your key...
   OPENAI_MODEL=gpt-4o-mini
   ```
   Test it: `python agent\llm_client.py` should print `Response: LLM connection working`.
   To go back to the free local model, set `LLM_PROVIDER=ollama`. Nothing else changes.
   Never share or upload `.env`: it holds your key.

1. Add the ingredient lists to your existing database:
   ```
   psql -U postgres -d glowcare -f database/migrations/001_add_ingredients.sql
   ```
   Safe to run twice. If `psql` isn't found, use its full path, e.g.
   `"C:\Program Files\PostgreSQL\16\bin\psql.exe"` (change `16` to your version).

2. Check it worked:
   ```
   python database\db.py
   ```
   The last line should be:
   `Ingredients (GC-P001): ['Water', 'Glycerin', 'Hyaluronic Acid', 'Niacinamide', 'Dimethicone', 'Phenoxyethanol']`

3. Rebuild the knowledge base (only needed if you haven't since the Phase 4 chunking fix):
   ```
   python rag\ingest.py
   ```

## Run it

Demo (one question per route, with full logs):
```
python -m agent.support_agent
```

The test sheet (run after EVERY change):
```
python -m tests.run_eval
```
Only some cases: `python -m tests.run_eval kb-uk db-price`

Each result is saved in `tests/results/` so you can compare runs.

## Reading the logs

```
[ROUTER] 'Do you sell products in the UK?' -> knowledge (general question -> knowledge base)
[LLM] Raw answer: ...                      <- what the model wrote
[CHECK] LLM answer REJECTED: ...           <- why the checker threw it away (if it did)
[CHECK] Using fallback: quoted_source      <- customer gets the policy text itself
[REPLY] (knowledge_base) ...               <- what the customer sees
```

## What the test results mean

- `db-*`, `clarify-*`, `esc-*`, `greeting` cases don't use the LLM, so they should
  **always** pass. If one fails, it's a bug in the code or the database. Fix it.
- `kb-*` cases use the LLM. A failure means the checker let a weak answer through or the
  retrieval found the wrong chunk. Look at `answer`, `checker` and the saved JSON.
- **Found a new mistake while chatting?** Add it as a case in `tests/eval_cases.json`. From then
  on it's checked automatically, forever.

## Settings you may tune later (Phase 10)

| Setting | File | Meaning |
|---|---|---|
| `MIN_GROUNDED_SHARE = 0.6` | `agent/verifier.py` | Share of answer words that must come from the source. Higher = stricter. |
| `QUOTE_MAX_DISTANCE = 0.75` | `agent/responder.py` | How close a chunk must be to be quoted as a fallback. |
| `REFUSAL_OVERRIDE_DISTANCE = 0.5` | `agent/responder.py` | If the model says "I don't know" but a chunk is this close, quote it instead. |
| `PRODUCT_ALIASES` | `agent/router.py` | Extra names customers use for products ("moisturizer", "spf"). |

## Known limits (honest list)

- The router uses keywords. An unusual phrasing ("what's the damage for the hydra stuff?")
  may fall through to the knowledge base, which then answers "I don't have that". That's safe
  but not ideal. Add the phrasing to the router and a test case when you see it.
- Escalation currently sets `escalate = True` and replies to the customer. Creating the actual
  escalation record needs a conversation ID, which arrives in Phase 7.
- The checker can't judge whether a grounded answer is *on topic*. The test sheet is what
  catches that.
