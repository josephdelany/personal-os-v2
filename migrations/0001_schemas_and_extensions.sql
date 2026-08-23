-- 0001_schemas_and_extensions.sql
-- Phase 2 spine. Forward-only. Schema-parameterised: the runner substitutes
-- __CORE__ (spine data) and __OPS__ (operational) so the identical DDL applies to
-- a throwaway core_dryrun/ops_dryrun pair first, then to core/ops for real.
--
-- Governing decisions: ADR-0013 (dedicated schema; public untouched, OQ-17),
-- ADR-0002/0019 (the atom). Only `public` existed before this migration and
-- `public.entities` (old cron stack) already occupies that name — the whole
-- reason the spine lives in its own schema.

CREATE SCHEMA IF NOT EXISTS __CORE__;
CREATE SCHEMA IF NOT EXISTS __OPS__;

-- btree_gist: lets a GiST index/exclusion mix scalar equality with range &&.
-- Available-but-not-installed on the live instance (verified 2026-08-23).
CREATE EXTENSION IF NOT EXISTS btree_gist;
-- gen_random_uuid() for server-side identity; pgcrypto is already installed.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
