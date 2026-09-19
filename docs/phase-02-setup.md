# Phase 2 — Setup & Verification

## What this phase adds
A real PostgreSQL database with the schema from `database/schema.sql`, seeded
with fictional demo data from `database/seed_data.sql`, plus a Python module
(`database/db.py`) that is the ONLY code in this project allowed to answer
price, stock, and order-status questions.

## How to run it locally

1. Install PostgreSQL locally if you don't have it (or use Docker — your
   call, not required for this phase).

2. Create the database:
   ```
   createdb glowcare
   ```
   (or, from psql: `CREATE DATABASE glowcare;`)

3. Load the schema and seed data:
   ```
   psql -d glowcare -f database/schema.sql
   psql -d glowcare -f database/seed_data.sql
   ```

4. Copy `.env.example` to `.env` and adjust `DB_USER`/`DB_PASSWORD` if your
   local Postgres isn't using the defaults.

5. Install the Python dependency:
   ```
   pip install -r requirements.txt
   ```

6. Run the smoke test:
   ```
   python database/db.py
   ```

## Expected output of the smoke test

```
Product lookup (Hydra Balance): {'product_id': 'GC-P001', 'name': 'Hydra Balance Moisturizer', ... 'price': 24.99, 'stock_quantity': 42, 'availability': 'in_stock', ...}
Price lookup (Niacinamide): {'price': 19.99, 'currency': 'USD'}
Availability (Niacinamide): {'availability': 'out_of_stock', 'stock_quantity': 0}
Order lookup (GC10241): {'order_id': 'GC10241', 'status': 'shipped', 'total_amount': 24.99, 'items': [{'quantity': 1, 'price_at_purchase': 24.99, 'product_name': 'Hydra Balance Moisturizer'}]}
Order lookup (GC99999 - should be None): None
```

If the last line prints `None` rather than an error or a guessed value,
that's the guardrail from `SYSTEM_RULES.md` rule 3 working correctly at the
data layer — the agent (built in later phases) can only pass along what this
function actually returns.

## Manual test questions for this phase

1. "How much is the Hydra Balance Moisturizer?" → should resolve to
   `get_product_price("Hydra Balance")` → $24.99, not an LLM guess.
2. "Is the Niacinamide Serum available?" → `get_product_availability(...)` →
   `out_of_stock`, `stock_quantity: 0`.
3. "Where is order GC10241?" → `get_order_status("GC10241")` → `shipped`.
4. "Where is order GC99999?" → `get_order_status("GC99999")` → `None`. This
   is the case Section 13 of the brief calls out explicitly — the system
   must say "not found," never invent a status.

## Note on scope

No agent, no LLM, and no chat interface touches this code yet. These are
plain Python functions you can call directly, as the smoke test does. Phase
5 (agent routing) is where these functions get wired up as callable "tools."
