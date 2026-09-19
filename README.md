# GlowCare AI Customer Support & Sales Agent (Local MVP)

A local, low-cost/free demo of an AI customer support and sales agent for a
**fictional** skincare company, GlowCare. Built as the foundation for a
real client-facing product — not a hardcoded chatbot.

> Everything under `/data` is fictional demo content, clearly labeled as such.
> No real company, products, or customers are represented.

## Architecture

```
Customer                                   Team (email)
   |                                              ^
Chat UI (Streamlit)     n8n webhook / (WhatsApp, Phase 12)   n8n: alerts, daily
   |                        |                                summary, reminders
   |                   Agent API (FastAPI, Phase 11)  -------------+
   |                        |
   +-----------+------------+
               |
AI Agent / Router
   |
   +--------------+------------------+-------------------+
   |              |                  |
  RAG          DB Tools        Human Escalation
   |              |                  |
 Chroma      PostgreSQL       Escalation Record
   |              |
Company      Products
Docs/FAQ/    Inventory
Policies     Orders
   +--------------+
          |
     LLM Response
          |
       Chat UI
```

**The core rule:** the LLM never invents business facts. Prices, stock, and
order status come from PostgreSQL. Policies, product descriptions, and
ingredient info come from retrieval over `/data` via Chroma. The LLM's job is
understanding the question, choosing the right source, and turning retrieved
facts into a natural-language reply. See `SYSTEM_RULES.md` for the exact
rules the agent will enforce.

## Why this split (RAG vs. DB vs. LLM)

- **RAG** = things that are *written down* and don't change per-customer
  (policies, product descriptions, FAQ, ingredient explanations).
- **Structured DB** = things that are *facts with a single current value*
  (a price, a stock count, an order's status) — these need exact lookups,
  not similarity search, so they live in PostgreSQL, not Chroma.
- **LLM** = the reasoning layer that decides which of the above to use and
  phrases the result — it never supplies facts on its own.

## Technology choices (and what's free vs. what isn't)

| Component      | Choice                          | Cost |
|-----------------|----------------------------------|------|
| LLM              | Ollama, local model (e.g. Llama 3 / Mistral) | Free, runs on your machine |
| Embeddings       | Local Hugging Face model (e.g. `all-MiniLM-L6-v2`) | Free |
| Vector store     | Chroma (local, file-based)      | Free |
| Structured DB    | PostgreSQL (local)               | Free |
| Backend          | Python (FastAPI only where needed) | Free |
| Frontend         | Streamlit                        | Free |
| Orchestration    | n8n, self-hosted (Phase 11)      | Free |
| Containerization | Docker (optional, added only if useful) | Free |

**Nothing in this MVP requires a paid API.** The only place a paid service
would plug in later is a cloud LLM (e.g. Claude) as a drop-in replacement for
Ollama if local model quality isn't sufficient for a real client demo — the
architecture is written so that swap doesn't require touching RAG, DB, or
routing code.

## Project structure

```
glowcare-agent/
├── frontend/         # Streamlit chat UI (Phase 6)
├── api/               # FastAPI: the agent as a web service for n8n (Phase 11)
├── agent/             # Router + LLM orchestration logic (Phase 4-5)
├── rag/                # Chunking, embedding, retrieval logic (Phase 3)
├── database/          # PostgreSQL schema + connection code (Phase 2)
├── data/
│   ├── products/      # products.json — structured demo product data
│   ├── policies/      # shipping/return/refund/cancellation/support policy docs
│   ├── faq/            # faq.md
│   └── docs/           # product_guide.md, ingredients_guide.md
├── n8n/                # 4 n8n workflows to import (Phase 11)
├── tests/              # Manual + automated test questions (Phase 10)
├── docs/               # Project documentation, logs of design decisions
├── SYSTEM_RULES.md    # Guardrails loaded into the agent's prompt at runtime
├── .env.example
├── requirements.txt
├── docker-compose.yml  # Added only if/when it earns its complexity
└── README.md
```

## Implementation phases

Each phase stops for approval before the next begins. Each phase also
includes 3-5 manual test questions you can run to verify it before moving on.

1. Project setup + fictional GlowCare data
2. PostgreSQL database (products, inventory, orders, customers)
3. RAG knowledge base (Chroma + local embeddings)
4. Local LLM + basic response generation
5. Agent routing (RAG vs. DB vs. clarify vs. escalate)
6. Local Streamlit chat UI
7. Human escalation flow
8. Conversation memory + logging
9. Business/admin dashboard
10. Testing + hallucination/guardrail evaluation
11. n8n integration ← latest (see docs/phase-11-setup.md)
12. Prepare architecture for WhatsApp (not implemented yet)

## What's real vs. mocked at this stage

Everything in this phase is **static demo data** — no code runs yet. Nothing
is "fake" in the sense of pretending to work; it simply doesn't exist yet.
Phase 2 is the first phase where running code appears (the PostgreSQL schema
and connection).
