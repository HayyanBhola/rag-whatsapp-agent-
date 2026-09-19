# Phase 4 — Setup & Verification

## What this phase adds
A real connection to a local LLM (via Ollama) that turns RAG-retrieved
chunks into natural-language, grounded answers — the first time an actual
answer gets generated in this project, rather than just retrieved data.

`agent/llm_client.py` — talks to Ollama's local HTTP API. No API key, no
internet call once the model is downloaded.

`agent/responder.py` — the full pipeline: retrieve chunks -> load
SYSTEM_RULES.md -> build a prompt that tells the LLM to answer ONLY from
those chunks -> call Ollama -> return the answer plus everything that went
into producing it (for auditability, per Section 14 of the brief).

## Install Ollama (one-time, outside Python)

Ollama is a separate program, not a pip package — it runs local models.

1. Download it from https://ollama.com/download (Windows installer).
2. Run the installer. It installs Ollama as a background service, so it
   starts automatically — you generally don't need to manually run
   `ollama serve`.
3. Pull the model this project uses:
   ```
   ollama pull qwen2.5:1.5b
   ```
   This is a genuinely small model (about 1.3GB download) — chosen
   deliberately because this machine has been low on free RAM during
   setup. It will answer more simply than a larger model, but it runs
   reliably without the memory issues we hit in Phase 3.

## Verify Ollama itself works (no Python yet)

```
ollama run qwen2.5:1.5b
```
Type a test message, confirm you get a response, then type `/bye` to exit.

## Run the Phase 4 smoke tests

1. Confirm the raw connection works:
   ```
   python agent\llm_client.py
   ```
   Expected: prints "Response: Ollama connection working" (or close to it
   — small models don't always follow instructions exactly word-for-word).

2. Run the full RAG -> LLM pipeline:
   ```
   python agent\responder.py
   ```
   This runs 3 test questions and prints, for each one: the RAG debug
   output (same as Phase 3), then the exact prompt sent to the LLM, then
   the model's final answer.

## What to check in the output

- **Question 1** (ingredients) — the answer should only mention ingredients
  that are actually in `ingredients_guide.md` / `product_guide.md`. If it
  names an ingredient not in those files, that's the model ignoring its
  instructions — worth flagging for Phase 10's hallucination testing.
- **Question 2** (return policy) — should match what `return_policy.md`
  actually says about opened products.
- **Question 3** ("Do you sell in the UK?") — GlowCare's documents never
  mention shipping regions. The answer should honestly say this isn't
  covered, NOT guess an answer. This is the most important one to check —
  it's a direct test of SYSTEM_RULES.md actually working.

## Note on scope

This phase does NOT yet decide whether to use RAG vs. the database vs.
escalate — every question here goes straight to RAG. That routing
decision is Phase 5. A price or order-status question asked right now
would incorrectly try to answer from documents (which don't have that
data) rather than querying PostgreSQL — that's expected and gets fixed
next phase, not a bug in this one.

## If Ollama installs but is slow

A 1B-parameter model should respond in a few seconds on most machines,
even CPU-only. If it takes much longer, close other memory-heavy programs
the same way we did for the RAG installs in Phase 3 — Ollama needs the
model's ~1.3GB to fit comfortably in free RAM to run at a normal speed.
