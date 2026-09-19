"""
frontend/app.py

Phase 6: the local chat UI. (Phase 8: messages are saved and the agent
remembers earlier messages in the same chat; both happen inside
handle_message, so this file only passes the conversation id.) A Streamlit page where you type a question and
see the agent's reply like a real chat.

Run it from the glowcare-agent folder:
    python -m streamlit run frontend/app.py

This file contains NO business logic. Every reply comes from
agent.support_agent.handle_message(), the same function the test sheet
checks, so the UI can never behave differently from what was tested.

Under each reply, "How this answer was found" shows the route, the database
rows or knowledge-base chunks used, what the LLM wrote, and whether the
answer checker accepted it (Section 14 of the brief: every answer must be
traceable).
"""

import json
import os
import sys

# Streamlit runs this file from inside frontend/, so point Python and the
# working directory at the project root. Without this, `import agent` and
# relative paths like "SYSTEM_RULES.md" and "rag/chroma_store" would fail.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import streamlit as st  # noqa: E402

from agent import llm_client  # noqa: E402
from agent.support_agent import handle_message, get_products  # noqa: E402
from database import db  # noqa: E402

st.set_page_config(page_title="GlowCare Assistant", layout="centered")

EXAMPLE_QUESTIONS = [
    "What ingredients are in the Hydra Balance Moisturizer?",
    "How much is the Niacinamide Serum and is it in stock?",
    "Where is my order GC10241?",
    "Can I return a product after opening it?",
    "Do you sell products in the UK?",
    "I got a rash after using the cleanser",
]

SOURCE_LABELS = {
    "database": "Answered from the database",
    "knowledge_base": "Answered from company documents",
    "fixed_reply": "Standard reply",
}
ANSWER_TYPE_LABELS = {
    "llm": "AI-written answer, passed all checks",
    "quoted_source": "AI answer rejected, so the policy text is quoted instead",
    "not_found": "Information not available",
}


# --- One-time startup ----------------------------------------------------
@st.cache_resource(show_spinner="Starting the assistant (first load can take ~30 seconds)...")
def warm_up():
    """Loads the product list and the search model once, so the first
    customer question isn't the slow one. Returns an error message, or None."""
    try:
        get_products()
        from rag.retriever import retrieve
        retrieve("warm up", verbose=False)
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


startup_error = warm_up()

if "messages" not in st.session_state:
    # Each item: {"role": "user"|"assistant", "content": str, "result": dict|None}
    st.session_state.messages = []


# --- Helpers ---------------------------------------------------------------
def to_json(value):
    """Database rows contain Decimal and datetime values, which st.json
    can't display directly; convert them to plain text first."""
    return json.loads(json.dumps(value, default=str))


def show_details(result: dict):
    """The "How this answer was found" panel under an assistant reply."""
    source = SOURCE_LABELS.get(result.get("source"), result.get("source"))
    st.caption(f"{source} · route: {result['route']}")
    if result.get("memory"):
        st.caption(f"Used earlier messages: {result['memory']}")
    if result.get("logging_error"):
        st.caption(f"Note: this exchange couldn't be saved ({result['logging_error']})")
    if result.get("escalate"):
        if result.get("escalation_id"):
            state = "created" if result.get("escalation_new") else "already open, same case"
            st.warning(f"Handed to a human team member: escalation "
                       f"ESC-{result['escalation_id']} {state} · priority "
                       f"{result.get('escalation_priority')}")
        elif result.get("escalation_error"):
            st.error("Flagged for a human, but the escalation couldn't be saved: "
                     f"{result['escalation_error']}")
        else:
            st.warning("Flagged for a human team member (not saved: this chat "
                       "has no conversation record).")

    with st.expander("How this answer was found"):
        st.markdown(f"**Route:** `{result['route']}` ({result['reason']})")
        details = result.get("details")

        if result["route"] == "database" and details:
            st.markdown("**Database rows used:**")
            st.json(to_json(details), expanded=False)

        elif result["route"] == "knowledge" and details:
            answer_type = details.get("answer_type")
            label = ANSWER_TYPE_LABELS.get(answer_type, answer_type)
            if details.get("llm_error"):
                label = ("AI service unavailable, so the policy text is quoted instead"
                         if answer_type == "quoted_source" else
                         "AI service unavailable and no strong match in the documents")
            st.markdown(f"**Result:** {label}")
            chunks = details.get("chunks_used") or []
            if chunks:
                st.markdown("**Document sections retrieved** (lower distance = closer match):")
                for i, c in enumerate(chunks, 1):
                    section = c.get("section") or c["text"].splitlines()[0]
                    st.markdown(f"{i}. {section} · `{c['source']}` · distance {c['distance']}")
            if details.get("llm_answer"):
                st.markdown("**What the AI wrote:**")
                st.text(details["llm_answer"])
            if details.get("problems"):
                st.markdown("**Why the AI answer wasn't used:**")
                for p in details["problems"]:
                    st.markdown(f"- {p}")
        else:
            st.markdown("No database or document lookup was needed.")


def current_conversation_id():
    """Each browser chat is one row in the conversations table, created on
    the first message (so opening the page doesn't create empty rows).
    Escalations are attached to it. If the database write fails, the chat
    still works; hand-offs just can't be saved."""
    if st.session_state.get("conversation_id") is None:
        try:
            st.session_state.conversation_id = db.create_conversation()
        except Exception:
            return None
    return st.session_state.conversation_id


def ask(question: str):
    """Sends one question to the agent and stores both sides of the exchange."""
    st.session_state.messages.append({"role": "user", "content": question, "result": None})
    try:
        result = handle_message(question, conversation_id=current_conversation_id(),
                                verbose=False)
        reply = result["answer"]
    except Exception as e:
        # A crash (database or AI provider down) is shown honestly, never
        # replaced with a made-up answer.
        result = None
        reply = ("Sorry, something went wrong on our side and I couldn't answer. "
                 f"(Technical detail: {type(e).__name__}: {e})")
    st.session_state.messages.append({"role": "assistant", "content": reply, "result": result})


# --- Sidebar -----------------------------------------------------------------
with st.sidebar:
    st.subheader("GlowCare Assistant")
    st.caption("Fictional demo company. No real products or customers.")

    st.markdown(f"**AI model:** {llm_client.LLM_PROVIDER} · `{llm_client.MODEL_NAME}`")
    cost = llm_client.estimated_cost_usd()
    calls = llm_client.usage_totals.get("calls", 0)
    if cost is not None:
        note = " at paid prices ($0 on Gemini's free tier)" if llm_client.LLM_PROVIDER == "gemini" else ""
        st.caption(f"AI calls since the app started: {calls} · est. cost ${cost:.4f}{note}")
    elif llm_client.LLM_PROVIDER == "ollama":
        st.caption("Local model: free.")

    st.divider()
    st.markdown("**Try asking**")
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, key=f"example-{q}", width="stretch"):
            ask(q)
            st.rerun()

    st.divider()
    if st.session_state.get("conversation_id"):
        st.caption(f"Conversation #{st.session_state.conversation_id}")
    if st.button("Clear chat", width="stretch"):
        if st.session_state.get("conversation_id"):
            try:
                db.close_conversation(st.session_state.conversation_id)
            except Exception:
                pass  # closing is bookkeeping only; never block the user
        st.session_state.messages = []
        st.session_state.conversation_id = None  # the next message starts a new conversation
        st.rerun()


# --- Main chat -----------------------------------------------------------------
st.title("GlowCare Assistant")
st.caption("Ask about our products, prices, stock, your order, or our shipping, "
           "return and refund policies.")

if startup_error:
    st.error("The assistant couldn't start. Check that PostgreSQL is running, "
             "`python rag/ingest.py` has been run, and your `.env` is set up.\n\n"
             f"Details: {startup_error}")
    st.stop()

if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown("Hi! I'm the GlowCare assistant. How can I help you today?")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg["result"]:
            show_details(msg["result"])

if question := st.chat_input("Type your question..."):
    with st.chat_message("user"):
        st.markdown(question)
    with st.spinner("Thinking..."):
        ask(question)
    st.rerun()
