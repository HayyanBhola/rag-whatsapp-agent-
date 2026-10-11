"""
tests/test_api_pytest.py

pytest entry point.

    pytest            fast, offline checks of the API's eval mode and metadata
    pytest -m slow    also runs the full script suites against the real
                      database: tests.test_api and the 118-case tests.run_eval
                      (the eval sheet calls the real LLM)

Slow tests are skipped, with the reason shown, when the database can't be
reached or the LLM key is missing, instead of failing.
"""

import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest import mock

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from agent import llm_client
from api import server

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


# --- Fast, offline ------------------------------------------------------------

def test_eval_mode_is_optional_and_off_by_default():
    assert server.ChatRequest(message="hi").eval_mode is False


def test_eval_mode_refused_without_configured_key():
    with mock.patch.object(server, "API_KEY", ""):
        r = TestClient(server.app).post("/chat", json={"message": "hi", "eval_mode": True})
    assert r.status_code == 403
    assert "GLOWCARE_API_KEY" in r.json()["detail"]


def test_eval_mode_refused_with_session_or_conversation():
    client = TestClient(server.app)
    key = {"X-API-Key": "k"}
    with mock.patch.object(server, "API_KEY", "k"):
        assert client.post("/chat", json={"message": "hi", "eval_mode": True},
                           headers={"X-API-Key": "wrong"}).status_code == 401
        for extra in ({"session_id": "s1"}, {"conversation_id": 1}):
            r = client.post("/chat", json={"message": "hi", "eval_mode": True, **extra}, headers=key)
            assert r.status_code == 422


def test_eval_mode_calls_agent_without_conversation():
    """Eval mode must take the test-sheet path (conversation_id=None), which
    never writes to the database, and must not open or close a chat."""
    fake = {"message": "hi", "route": "greeting", "reason": "greeting", "intents": [],
            "answer": "Hi!", "source": "fixed_reply", "escalate": False,
            "escalation_id": None, "memory": None, "details": None}
    with mock.patch.object(server, "API_KEY", "k"), \
         mock.patch("agent.support_agent.handle_message", return_value=fake) as handle, \
         mock.patch.object(server, "_new_conversation") as new_chat, \
         mock.patch.object(server.nt, "find_or_create_conversation") as find_chat:
        r = TestClient(server.app).post("/chat", json={"message": "hi", "eval_mode": True},
                                        headers={"X-API-Key": "k"})
    assert r.status_code == 200
    assert handle.call_args.kwargs["conversation_id"] is None
    new_chat.assert_not_called()
    find_chat.assert_not_called()
    body = r.json()
    assert body["conversation_id"] is None and body["eval_mode"] is True
    assert body["retrieved_chunks"] is None and body["prompt_tokens"] is None


def test_retrieved_chunks_mapping():
    result = {"route": "knowledge", "details": {"chunks_used": [
        {"id": "refund_policy.md-2", "text": "t", "source": "refund_policy.md",
         "section": "s", "distance": 0.41}]}}
    assert server._retrieved_chunks(result) == [
        {"id": "refund_policy.md-2", "text": "t", "score": 0.41, "source": "refund_policy.md"}]
    assert server._retrieved_chunks({"route": "database", "details": [{"price": 1}]}) is None


def test_request_usage_counts_per_thread():
    llm_client.reset_request_usage()
    assert llm_client.request_usage() == {"prompt_tokens": None, "completion_tokens": None}
    llm_client._record_request_usage(100, 20)
    llm_client._record_request_usage(5, None)
    seen_elsewhere = {}
    t = threading.Thread(target=lambda: seen_elsewhere.update(llm_client.request_usage()))
    t.start()
    t.join()
    assert llm_client.request_usage() == {"prompt_tokens": 105, "completion_tokens": 20}
    assert seen_elsewhere == {"prompt_tokens": None, "completion_tokens": None}


# --- Slow: the real script suites ---------------------------------------------

def _database_problem():
    try:
        from database import db
        with db.get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return None
    except Exception as e:
        return f"database not reachable ({type(e).__name__}); check DB_* in .env"


def _llm_key_problem():
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    if provider == "ollama":
        return None
    name = f"{provider.upper()}_API_KEY"
    value = os.getenv(name, "").strip()
    if not value or value.startswith(("paste-", "sk-paste-")):
        return f"{name} is not set in .env (LLM_PROVIDER={provider})"
    return None


def _run_script(module, *args, timeout):
    proc = subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-40:])
    assert proc.returncode == 0, f"python -m {module} failed:\n{tail}"
    return proc.stdout


@pytest.mark.slow
def test_api_script_suite():
    if problem := _database_problem():
        pytest.skip(problem)
    _run_script("tests.test_api", timeout=600)


@pytest.mark.slow
def test_eval_sheet_all_cases_pass():
    if problem := _database_problem() or _llm_key_problem():
        pytest.skip(problem)
    # run_eval exits 0 only when every case passed.
    _run_script("tests.run_eval", timeout=3600)
