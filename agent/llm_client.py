"""
agent/llm_client.py

The ONLY place in this project that talks to an LLM. Three providers are
supported, chosen by LLM_PROVIDER in your .env file:

    LLM_PROVIDER=gemini   -> Google Gemini API (free tier; needs GEMINI_API_KEY)
    LLM_PROVIDER=openai   -> OpenAI API (paid, per token; needs OPENAI_API_KEY)
    LLM_PROVIDER=ollama   -> local Ollama (free, runs on your machine)

Nothing else in the project knows or cares which one is running: the
router, database, answer checker and test sheet work the same with all.
That's the "drop-in replacement" the README planned for.

WHY HOSTED MODELS WERE ADDED (Phase 5): qwen2.5:1.5b, the largest model this
machine's RAM could run, kept ignoring instructions. A small hosted model
(gpt-4o-mini) costs about $0.0003 per answer and follows instructions far
better. Gemini was added next because its free tier costs nothing.
Ollama stays as a free/offline fallback.

All providers fail loudly with a clear error rather than silently
returning something that looks like a real answer.
"""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

# --- OpenAI -------------------------------------------------------------
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
# gpt-4o-mini: cheap, fast, and supports temperature 0 (repeatable answers).
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# --- Gemini -------------------------------------------------------------
# Google offers an OpenAI-compatible endpoint, so Gemini reuses the exact
# same request code as OpenAI; only the URL, key and model name differ.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# gemini-3.1-flash-lite: the cheapest current model, and free on the free tier.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()

# --- Ollama -------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
# qwen2.5:1.5b: the largest model that fit in this machine's free RAM
# (llama3.2:1b hit out-of-memory errors; qwen2.5:0.5b was too weak).
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b").strip()

# Kept so older code/imports that used MODEL_NAME still work.
MODEL_NAME = {"openai": OPENAI_MODEL, "gemini": GEMINI_MODEL}.get(LLM_PROVIDER, OLLAMA_MODEL)

class LLMUnavailableError(RuntimeError):
    """The AI service is temporarily unreachable or overloaded (HTTP 500/502/
    503/504, a timeout, no connection), even after retrying. Not a setup
    mistake. agent/responder.py catches this one and answers from the
    documents without AI instead of crashing the chat. Setup errors (wrong
    key, wrong model name) stay plain RuntimeErrors so they are noticed."""


# Server-side "try again later" codes. Seen for real in Phase 10: Gemini
# returned "503 This model is currently experiencing high demand" twice
# during one test run.
TRANSIENT_STATUS = {500, 502, 503, 504}
# Waits before each retry (seconds). 429 = rate limit (free tier allows only
# a few requests per minute); 5xx = the provider is overloaded.
RATE_LIMIT_WAITS = [15, 30, 45]
OVERLOAD_WAITS = [5, 15, 30]

# Answers are 1-3 sentences; this cap stops a runaway answer from
# costing money or time.
MAX_ANSWER_TOKENS = 300


def _call_chat_api(provider, url, api_key, model, prompt, system_prompt, timeout):
    """One request to an OpenAI-style chat API (OpenAI itself, or Gemini's
    OpenAI-compatible endpoint)."""
    key_name = f"{provider.upper()}_API_KEY"
    if not api_key:
        raise RuntimeError(
            f"LLM_PROVIDER is '{provider}' but {key_name} is empty. Add your key "
            f"to the .env file ({key_name}=...), or change LLM_PROVIDER."
        )
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": model, "messages": messages,
               "max_completion_tokens": MAX_ANSWER_TOKENS}
    if provider == "gemini":
        # Gemini 3 models always "think" before answering, and that thinking
        # uses the same token budget, so allow more room and keep it short.
        # Google recommends leaving Gemini 3's temperature at its default.
        payload["max_completion_tokens"] = 2000
        payload["reasoning_effort"] = "low"
        if model.startswith("gemini-2"):
            payload["temperature"] = 0
    elif model.startswith(("gpt-5", "o1", "o3", "o4")):
        # OpenAI reasoning models reject a custom temperature and also spend
        # hidden "thinking" tokens from the same budget.
        payload["max_completion_tokens"] = 2000
    else:
        # temperature 0 = the same question gives the same answer every run.
        payload["temperature"] = 0
        payload["seed"] = 42

    # Temporary problems are retried after a pause instead of failing:
    # 429 (rate limit) and 500/502/503/504 (provider overloaded or down),
    # plus timeouts and dropped connections.
    attempt = 0
    while True:
        try:
            response = requests.post(
                url, json=payload, timeout=timeout,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            status, error = response.status_code, None
        except requests.exceptions.RequestException as e:
            response, status, error = None, None, e
        waits = RATE_LIMIT_WAITS if status == 429 else OVERLOAD_WAITS
        transient = error is not None or status in TRANSIENT_STATUS or status == 429
        if not transient or attempt >= len(waits):
            break
        what = ("rate limit hit" if status == 429 else
                f"busy (error {status})" if status else "not reachable")
        print(f"[LLM] {provider} {what}, waiting {waits[attempt]}s and retrying "
              f"({attempt + 1}/{len(waits)})...")
        time.sleep(waits[attempt])
        attempt += 1

    if error is not None:
        raise LLMUnavailableError(f"Could not reach the {provider} API after {attempt + 1} tries. "
                                  f"Check your internet connection. Original error: {error}") from error

    if response.status_code != 200:
        try:
            body = response.json()
            if isinstance(body, list):  # Gemini sometimes wraps errors in a list
                body = body[0]
            detail = body.get("error", {}).get("message", response.text)
        except (ValueError, AttributeError, IndexError):
            detail = response.text
        key_page = {"openai": "platform.openai.com/api-keys",
                    "gemini": "aistudio.google.com/apikey"}[provider]
        hints = {
            400: f"Check {key_name} and the model name in .env.",
            401: f"Your {key_name} is wrong or was revoked. Copy it again from {key_page}.",
            403: f"Your {key_name} isn't allowed to use this API. Copy it again from {key_page}.",
            404: f"The model '{model}' doesn't exist or your account can't use it. "
                 f"Check {provider.upper()}_MODEL in .env.",
            429: "Rate limit still hit after retrying, or your quota/credit is used up.",
            503: "The provider is overloaded right now. This is on their side and usually "
                 "passes within minutes.",
        }
        error_class = LLMUnavailableError if response.status_code in TRANSIENT_STATUS else RuntimeError
        raise error_class(f"{provider} returned error {response.status_code}"
                          + (f" after {attempt + 1} tries" if attempt else "") + ". "
                          f"{hints.get(response.status_code, '')} Details: {detail}")

    data = response.json()
    answer = data["choices"][0]["message"].get("content") or ""
    usage = data.get("usage") or {}
    _record_usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
    return answer.strip()


def _call_ollama(prompt: str, system_prompt: str, timeout: int) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system_prompt,
        # temperature 0 = always pick the most likely next word, so the same
        # question gives the same answer every run.
        "options": {"temperature": 0, "seed": 42},
        "stream": False,
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise LLMUnavailableError(
            "Could not reach Ollama at http://localhost:11434 (or it timed out). "
            "Is Ollama running? Start it with `ollama serve` "
            "(or it may already be running as a background service — "
            "check with `ollama list`)."
        ) from e
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(
            f"Ollama returned an error. Is the model '{OLLAMA_MODEL}' pulled? "
            f"Run `ollama pull {OLLAMA_MODEL}` if not. Original error: {e}"
        ) from e
    return response.json()["response"].strip()


# --- Token counter (OpenAI / Gemini) -------------------------------------
# Running totals for this Python process, so tests/run_eval.py can print
# what a run cost. Prices are per 1M tokens (input, output) — check
# openai.com/api/pricing, they change.
PRICES_PER_MILLION = {
    # Gemini: these are PAID-tier prices. On the free tier you pay $0.
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
}
usage_totals = {"input_tokens": 0, "output_tokens": 0, "calls": 0}


def _record_usage(input_tokens: int, output_tokens: int):
    usage_totals["input_tokens"] += input_tokens
    usage_totals["output_tokens"] += output_tokens
    usage_totals["calls"] += 1


def estimated_cost_usd():
    """Estimated spend for this run in USD, or None if the model's price
    isn't in PRICES_PER_MILLION (or the provider is Ollama, which is free)."""
    if LLM_PROVIDER not in ("openai", "gemini") or MODEL_NAME not in PRICES_PER_MILLION:
        return None
    price_in, price_out = PRICES_PER_MILLION[MODEL_NAME]
    return (usage_totals["input_tokens"] * price_in
            + usage_totals["output_tokens"] * price_out) / 1_000_000


def call_llm(prompt: str, system_prompt: str = "", timeout: int = 60) -> str:
    """Sends one prompt to whichever provider LLM_PROVIDER selects and
    returns the model's text answer."""
    if LLM_PROVIDER == "openai":
        return _call_chat_api("openai", OPENAI_URL, OPENAI_API_KEY, OPENAI_MODEL,
                              prompt, system_prompt, timeout)
    if LLM_PROVIDER == "gemini":
        return _call_chat_api("gemini", GEMINI_URL, GEMINI_API_KEY, GEMINI_MODEL,
                              prompt, system_prompt, timeout)
    if LLM_PROVIDER == "ollama":
        return _call_ollama(prompt, system_prompt, timeout)
    raise RuntimeError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}' in .env. "
                       "Use 'gemini', 'openai' or 'ollama'.")


# Old name, kept so nothing that imported call_ollama breaks.
call_ollama = call_llm


if __name__ == "__main__":
    # Smoke test — confirms the chosen provider answers, no RAG involved.
    print(f"Provider: {LLM_PROVIDER} | model: {MODEL_NAME}")
    answer = call_llm(
        prompt="Say 'LLM connection working' and nothing else.",
        system_prompt="You are a test assistant. Follow instructions exactly.",
    )
    print(f"Response: {answer}")
    if LLM_PROVIDER in ("openai", "gemini"):
        cost = estimated_cost_usd()
        print(f"Tokens used: {usage_totals} | est. cost: "
              + (f"${cost:.6f}" if cost is not None else "unknown for this model"))
