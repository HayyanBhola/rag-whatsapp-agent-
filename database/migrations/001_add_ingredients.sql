-- Migration 001: store each product's full ingredient list in PostgreSQL.
-- (FICTIONAL DEMO DATA — values mirror data/products/products.json)
--
-- WHY: in Phase 4 the LLM listed ceramides and zinc PCA as Hydra Balance
-- ingredients because it read them from the general ingredients guide.
-- Ingredient lists are exact facts, like prices, so they belong in the
-- database, where the agent reads them directly and nothing can be guessed.
--
-- Safe to run more than once.
--   psql -U postgres -d glowcare -f database/migrations/001_add_ingredients.sql

ALTER TABLE products ADD COLUMN IF NOT EXISTS ingredients TEXT[] NOT NULL DEFAULT '{}';

UPDATE products SET ingredients = ARRAY['Water', 'Glycerin', 'Hyaluronic Acid', 'Niacinamide', 'Dimethicone', 'Phenoxyethanol'] WHERE product_id = 'GC-P001';
UPDATE products SET ingredients = ARRAY['Water', 'Ceramide NP', 'Cholesterol', 'Fatty Acids', 'Shea Butter', 'Squalane'] WHERE product_id = 'GC-P002';
UPDATE products SET ingredients = ARRAY['Water', 'Niacinamide 10%', 'Zinc PCA', 'Glycerin', 'Panthenol'] WHERE product_id = 'GC-P003';
UPDATE products SET ingredients = ARRAY['Water', 'Coco-Glucoside', 'Glycerin', 'Panthenol', 'Allantoin'] WHERE product_id = 'GC-P004';
UPDATE products SET ingredients = ARRAY['Water', 'Zinc Oxide', 'Titanium Dioxide', 'Glycerin', 'Dimethicone'] WHERE product_id = 'GC-P005';
