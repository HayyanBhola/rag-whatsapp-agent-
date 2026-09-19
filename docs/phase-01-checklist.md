# Phase 1 — Verification Checklist

Phase 1 has no running code, so "testing" here means manually checking the
content is coherent and complete before we build on top of it.

## Manual checks
1. Open `data/products/products.json` — do all 5 products have every field
   (price, ingredients, stock, availability)? Is one product marked
   `out_of_stock` on purpose (Niacinamide Serum) so later phases have a
   real "not available" case to handle?
2. Open `data/policies/return_policy.md` — does it clearly state the
   opened-vs-unopened distinction? This matters for Scenario 5/8-style
   edge cases later.
3. Open `SYSTEM_RULES.md` — do the 10 rules cover every guardrail listed in
   Section 13 of the project brief (prices, ingredients, availability, order
   status, policies, no medical claims)?
4. Confirm every document under `/data` has a visible "FICTIONAL DEMO
   DOCUMENT" label.

If all four check out, Phase 1 is approved and Phase 2 (PostgreSQL schema +
products/inventory/orders) can start.

## Planned database schema (for Phase 2 — not yet implemented)

This is a preview so you can review the shape before any SQL is written:

- **customers**(customer_id, name, email, created_at)
- **products**(product_id, name, description, price, stock_quantity,
  availability) — mirrors `products.json`, becomes the source of truth once
  Phase 2 starts; `products.json` will be the seed data loaded into this table.
- **inventory** — merged into `products.stock_quantity` for simplicity unless
  multi-warehouse tracking is needed later (flag if you want it split out).
- **orders**(order_id, customer_id, status, created_at)
- **order_items**(order_item_id, order_id, product_id, quantity, price_at_purchase)
- **conversations**(conversation_id, customer_id, started_at, status)
- **messages**(message_id, conversation_id, sender, content, intent, created_at)
- **escalations**(escalation_id, conversation_id, reason, created_at, status)

Phase 2 test questions (for when we get there):
1. "Where is my order GC10241?" → should return a real row, not a guess.
2. "Where is my order GC99999?" → should return "not found," not a hallucinated status.
3. "Is the Niacinamide Serum available?" → should return `out_of_stock` from the DB.
4. "How much is the Hydra Balance Moisturizer?" → exact price from DB, not from the LLM.
