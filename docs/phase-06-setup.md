# Phase 6 — Local Chat UI (Streamlit)

## What this phase adds

`frontend/app.py`: a chat web page that runs on your own computer.

- Type a question → the agent replies like a real chat.
- Under every reply: where the answer came from (database, company
  documents, or a standard reply), and a **"How this answer was found"**
  panel showing the route, the database rows or document sections used,
  what the AI wrote, and whether the answer checker accepted it.
- Replies flagged for a human show a yellow notice.
- Sidebar: which AI model is running, estimated AI cost since the app
  started, example questions you can click, and a "Clear chat" button.

The page contains **no business logic**. Every reply comes from
`handle_message()` in `agent/support_agent.py`, the same function the test
sheet checks. So the UI can't answer differently from what was tested.

## Setup (one time)

From the `glowcare-agent` folder:
```
pip install streamlit
```
(Install only Streamlit. Re-running `pip install -r requirements.txt` on
Python 3.13 tries to rebuild the pinned chromadb and fails without a C++
compiler.)

`.streamlit/config.toml` turns off Streamlit's file watcher. Without it,
Streamlit prints `No module named 'torchvision'` errors because it scans the
`transformers` library. After editing code, refresh the browser yourself.

## Run it

```
python -m streamlit run frontend/app.py
```
Your browser opens at http://localhost:8501. The first load takes up to
~30 seconds (it loads the search model once). Stop the app with **Ctrl+C**
in PowerShell.

Before starting, PostgreSQL must be running and `.env` must be set up
(same as Phase 5). If something is missing, the page shows a red message
saying what to check instead of crashing.

## Manual test questions for this phase

Click each example in the sidebar, or type them:

1. "What ingredients are in the Hydra Balance Moisturizer?" → the exact list
   from the database. Caption: *Answered from the database*.
2. "Where is my order GC10241?" → *shipped*, 1 x Hydra Balance Moisturizer.
3. "Can I return a product after opening it?" → only after an adverse reaction
   or if it arrived damaged/defective. Open **How this answer was found**: you
   should see the Return Policy sections and *AI-written answer, passed all checks*.
4. "I got a rash after using the cleanser" → handed to a human, yellow notice.
5. "How much does it cost?" → asks which product.

## What this phase does NOT do yet

- Chats are not saved: refreshing the page or "Clear chat" starts over.
  Saving conversations and messages to PostgreSQL is **Phase 8**.
- Each question is answered on its own: "how much is it?" after asking about
  the serum doesn't know "it" = the serum. Conversation memory is **Phase 8**.
- The human hand-off notice doesn't create an escalation record yet: **Phase 7**.
