# ADR-0039: hypothesis_register status gains CANDIDATE

## Status
Accepted

## Date
2026-09-01

## Decision
Migration 0027 widens the status CHECK to include 'CANDIDATE'. REQ-INF-401 and
REQ-TIER-053 require scan/generator output to live in hypothesis_register as
CANDIDATE (the EXPLORATORY surface's sole source); the 0010 CHECK predates those
requirements. Not a RULE-00 weakening: no gate or threshold moves; a
spec-required member is added by recorded decision. Freeze trigger untouched;
CANDIDATE rows carry scan-run metadata in the prereg columns and are converted
to real registrations only by inserting a NEW row at Watch time.
