-- 0066_inferred_inputs.sql — a conclusion built on a conclusion says so, and cannot outrank it
-- (REQ-REC-016 inferred-input propagation, INV-5; ADR-0135).
--
-- THE GAP. `core.inferred_events` recorded WHAT was concluded and from which method, and had no
-- way to record that an input was itself a conclusion. Every citation in `core.event_evidence`
-- was implicitly a measurement. So the one acceptance case REQ-REC-016 names by the words
-- "inferred-input propagation" could not be executed at all: there was nothing to propagate
-- through, and the test that claimed to cover it passed a dictionary of labels to a reporting
-- function.
--
-- WHY A CAP AND NOT A WARNING. Without the cap, inferences promote each other. Infer A at
-- DESCRIPTIVE from one source; infer B from A and a second DESCRIPTIVE inference A'; B now has
-- two independent supporting origins and reaches EXPLORATORY. The system then believes B more
-- strongly than any measurement ever supported, and every row in the chain is individually
-- defensible. The cap is the WEAKEST input rather than an average, because averaging lets a
-- strong input launder a weak one.
--
-- WHY IN THE DATABASE AND NOT ONLY IN PYTHON. tools/engines/reconstruct.py applies the same cap
-- and is the first line of defence. It is not the only writer this table will ever have, and a
-- rule that lives only in the writer is a rule that lasts until the second writer.

ALTER TABLE __CORE__.inferred_events
    ADD COLUMN IF NOT EXISTS inferred_inputs text[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN __CORE__.inferred_events.inferred_inputs IS
    'Refs of the supporting citations that were themselves conclusions, not measurements. '
    'Empty means every input was measured. REQ-REC-016, INV-5.';

-- An event resting on an inference may not sit at the top reconstruction tier. EXPLORATORY here
-- means "two independent sources corroborate", and two conclusions are not two sources.
ALTER TABLE __CORE__.inferred_events
    ADD CONSTRAINT inferred_input_caps_the_tier
    CHECK (cardinality(inferred_inputs) = 0 OR tier <> 'EXPLORATORY');
