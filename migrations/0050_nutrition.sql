-- 0050_nutrition.sql — B12: food and drink resolution (REQ-NUT §D/§E; ADR-0056).
--
-- Today a food capture becomes a `consume` atom with a label and no nutrients. After this,
-- a resolvable item carries kcal / protein / carbs / fat / ethanol as INTERVALS whose width
-- is a function of how the value was obtained (RULE-08), and an unresolvable one stays a
-- documented gap rather than becoming a plausible number (RULE-06, REQ-NUT-040).
--
-- The one number the whole subsystem exists to avoid: a single kcal figure. Text-only LLM
-- recall carries 652 kcal MAE and frontier vision ~36% MAPE with systematic downward bias,
-- so a point estimate is a lie about precision. Every width below is from the spec verbatim.

-- ---------------------------------------------------------------- what may be called at all
-- RULE-29 names the only destinations personal data may reach. An allowlist in the database
-- rather than in code, so adding a destination is a visible data change reviewable on its own.
CREATE TABLE IF NOT EXISTS config.egress_allowlist (
    host        TEXT PRIMARY KEY,
    purpose     TEXT NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    note        TEXT
);
INSERT INTO config.egress_allowlist (host, purpose, note) VALUES
 ('api.nal.usda.gov',      'nutrition', 'USDA FoodData Central; free API key, no personal data in the request'),
 ('world.openfoodfacts.org','nutrition', 'Open Food Facts; no key, User-Agent required (REQ-NUT-010)'),
 ('api.cloudflare.com',    'model',     'Workers AI; the only model destination (ADR-0063)')
ON CONFLICT (host) DO NOTHING;

-- ---------------------------------------------------------------- the cache, which comes first
-- REQ-NUT §D.1. A lookup that has been done once is never done again: it costs a request, it
-- can fail, and the answer does not change. `raw` keeps the source payload so a later change
-- of interpretation can be re-derived without re-fetching.
CREATE TABLE IF NOT EXISTS __CORE__.foods_cache (
    food_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name      TEXT NOT NULL,
    source              TEXT NOT NULL CHECK (source IN ('usda_branded','usda_foundation','off_product','joe')),
    source_id           TEXT,
    brand               TEXT,
    nutrients_per_100g  JSONB NOT NULL,
    serving_g           NUMERIC CHECK (serving_g IS NULL OR serving_g > 0),
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                 JSONB,
    UNIQUE (canonical_name, source, source_id)
);
CREATE INDEX IF NOT EXISTS foods_cache_name_idx ON __CORE__.foods_cache (lower(canonical_name));

-- REQ-NUT §D.4. Joe's own portions outrank every source: a correction is permanent (RULE-10).
CREATE TABLE IF NOT EXISTS __CORE__.portions (
    portion_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT NOT NULL,
    grams          NUMERIC NOT NULL CHECK (grams > 0),
    source         TEXT NOT NULL DEFAULT 'joe' CHECK (source IN ('joe','usda','off','portion_table')),
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    note           TEXT
);
CREATE INDEX IF NOT EXISTS portions_name_idx ON __CORE__.portions (lower(canonical_name), source);

-- REQ-NUT §D.5. An item nothing could resolve is a row here, not a guess. THE DESK lists it.
CREATE TABLE IF NOT EXISTS __CORE__.unresolved_items (
    item_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_capture_id UUID REFERENCES __CORE__.raw_captures(capture_id),
    item_text      TEXT NOT NULL,
    subject_day    DATE NOT NULL,
    tried          JSONB NOT NULL DEFAULT '[]'::jsonb,   -- which sources were asked, and what they said
    seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at    TIMESTAMPTZ,
    resolved_by    TEXT CHECK (resolved_by IS NULL OR resolved_by IN ('joe','later_source'))
);
CREATE INDEX IF NOT EXISTS unresolved_items_open_idx
    ON __CORE__.unresolved_items (subject_day) WHERE resolved_at IS NULL;

-- ---------------------------------------------------------------- width is a function of method
-- REQ-NUT-035..040, verbatim. Stored rather than coded because RULE-00 forbids quietly editing
-- a threshold, and a width in a table is a visible data change with a diff.
CREATE TABLE IF NOT EXISTS config.nutrition_interval_widths (
    method     TEXT PRIMARY KEY,
    rel_low    NUMERIC NOT NULL CHECK (rel_low > 0 AND rel_low <= 1),
    rel_high   NUMERIC NOT NULL CHECK (rel_high >= 1),
    requirement TEXT NOT NULL,
    note       TEXT
);
INSERT INTO config.nutrition_interval_widths (method, rel_low, rel_high, requirement, note) VALUES
 ('weighed',        0.90, 1.10, 'REQ-NUT-035', 'provisionally equal to labelled (ADR-0005): weighing removes portion error, not composition error'),
 ('labelled',       0.90, 1.10, 'REQ-NUT-036', 'label legal tolerance'),
 ('usda_branded',   0.90, 1.10, 'REQ-NUT-036', 'a branded USDA entry is the label'),
 ('usda_foundation',0.80, 1.20, 'REQ-NUT-037', 'generic composition, portion inferred'),
 ('off_product',    0.90, 1.10, 'REQ-NUT-036', 'crowd-sourced label transcription'),
 ('portion_table',  0.80, 1.20, 'REQ-NUT-037', NULL),
 ('joe',            0.90, 1.10, 'REQ-NUT-036', 'a correction Joe made; still not a measurement'),
 -- REQ-NUT-038/039: ASYMMETRIC, and wider above than below, because the documented
 -- photo-estimation bias is systematic UNDER-estimation. Symmetric would encode the wrong shape.
 ('photo_estimate', 0.75, 1.60, 'REQ-NUT-038', 'asymmetric: documented bias is systematic underestimation')
ON CONFLICT (method) DO NOTHING;

-- The named provisional constant, in the open. REQ-NUT-068 calls it a placeholder; a number
-- in a config row can be re-ruled, a number inlined in code gets copied instead.
INSERT INTO config.strings (key, value, note) VALUES
 ('g_per_standard_drink', '14', 'REQ-NUT-068: provisional, US NIAAA standard drink'),
 ('ethanol_density_g_per_ml', '0.789', 'ADR-0030 / REQ-NUT-066: density of ethanol')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------- the metrics themselves
INSERT INTO __CORE__.metric_registry
  (metric_key, display_name, family, unit, state_class, expected_cadence,
   max_staleness_days, plausible_low, plausible_high, self_report)
VALUES
  ('kcal',        'Energy',        'nutrition', 'kcal', 'total', 'daily', 3, 0, 12000, false),
  ('protein_g',   'Protein',       'nutrition', 'g',    'total', 'daily', 3, 0,   800, false),
  ('carbs_g',     'Carbohydrate',  'nutrition', 'g',    'total', 'daily', 3, 0,  2000, false),
  ('fat_g',       'Fat',           'nutrition', 'g',    'total', 'daily', 3, 0,   800, false),
  ('fiber_g',     'Fibre',         'nutrition', 'g',    'total', 'daily', 3, 0,   300, false),
  ('sugar_g',     'Sugar',         'nutrition', 'g',    'total', 'daily', 3, 0,  1500, false),
  ('sodium_mg',   'Sodium',        'nutrition', 'mg',   'total', 'daily', 3, 0, 40000, false)
ON CONFLICT (metric_key) DO NOTHING;

COMMENT ON TABLE __CORE__.foods_cache IS
  'REQ-NUT §D.1. Cache-first: a lookup done once is never repeated. `raw` keeps the source '
  'payload so a changed interpretation can be re-derived without re-fetching.';
COMMENT ON TABLE config.nutrition_interval_widths IS
  'REQ-NUT-035..040 verbatim. A width in a table is a visible data change; a width in code '
  'gets edited to make something pass (RULE-00).';
