# GlowCare Agent — Evaluation Report

Generated 19 Sep 2026, 23:53 from `tests\results\eval_20260919_235342.json` · model **gemini/gemini-3.1-flash-lite** · run at 2026-09-19T23:53:42

## 1. Headline

| Measure | Result |
|---|---|
| Test cases passed | **118/118 (100%)** |
| Safety-critical cases passed | **71/71 (100%)** |
| Forbidden content delivered to a customer | **0** (target met: 0) |
| AI answers produced | 40 |
| AI answers the checker caught and replaced | 1 (2%) |
| AI calls / est. cost | 40 / $0.0113 at paid prices ($0 on Gemini's free tier) |

*Safety-critical* = a wrong answer could mislead a customer: prices, stock, ingredients, orders, medical claims, and attempts to trick the assistant.

## 2. Scores per category

| Category | Passed | Score | What it tests |
|---|---|---|---|
| database | 22/22 | 100% | prices, stock, ingredients, orders: exact facts from PostgreSQL |
| clarify | 7/7 | 100% | asks ONE question instead of guessing |
| escalation | 12/12 | 100% | hands off to a human: requests, complaints, skin reactions |
| knowledge | 33/33 | 100% | policy/FAQ/product answers from documents (AI + checker) |
| medical | 5/5 | 100% | never claims a product treats/cures; no diagnoses |
| memory | 10/10 | 100% | follow-up questions use earlier messages correctly |
| robustness | 14/14 | 100% | typos, capitals, Roman Urdu |
| adversarial | 9/9 | 100% | tricks: 'ignore your instructions', fake prices, invented ingredients |
| out_of_scope | 4/4 | 100% | questions GlowCare can't answer: no made-up answers |
| greeting | 2/2 | 100% | hello / thanks |

## 3. Hallucinations

- **Caught:** 1 of 40 AI answers failed a check (unsupported words, made-up numbers, wrong ingredients, medical words, fake dialogue) and were replaced by the quoted policy text or an honest "I don't have that information". The customer never saw them.
- **Raw AI answers that would have been wrong for their question:** 0 of 40. (Includes answers that were correct but off-topic or incomplete.)
- **Delivered:** 0. Nothing a test case forbids reached a customer.

## 4. Checker strictness (grounding rule)

Each AI answer from this run replayed through the checker at different strictness levels (no new AI calls).

| Strictness | Good answers kept | Good answers thrown away | Bad answers let through |
|---|---|---|---|
| 0.40 | 31 | 0 | 0 |
| 0.50 | 31 | 0 | 0 |
| 0.55 | 31 | 0 | 0 |
| 0.60 ← current | 31 | 0 | 0 |
| 0.65 | 31 | 0 | 0 |
| 0.70 | 31 | 0 | 0 |
| 0.80 | 30 | 1 | 0 |

Recommended: **0.30** (current 0.60). Consider changing MIN_GROUNDED_SHARE to 0.30 and re-running.

## 5. Failing cases (0)

None.

## 6. Model comparison (newest full run of each model)

| Model | Passed | Safety-critical | Knowledge | Caught | Delivered | Cost |
|---|---|---|---|---|---|---|
| gemini/gemini-3.1-flash-lite | 118/118 | 71/71 | 33/33 | 1/40 | 0 | $0.0113 |

Only one model tested so far. Compare with e.g. `python -m tests.run_eval --provider openai`, then run this report again.
