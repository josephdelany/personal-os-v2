# Rule: the constitution has a hard size cap

Applies to: `docs/CONSTITUTION.md`

RULE-00 is the meta-rule and is exempt from the count. Numbered rules RULE-01
through RULE-30 are capped at **30**. Adding a thirty-first numbered rule
requires removing one first, in the same commit, with the removal justified in
an ADR.

The cap exists because the previous specification reached 617 KB and its own
precedence chain then contradicted itself in at least three places. A rule set
nobody can hold in their head is not a rule set.

`tools/validate_layout.py` enforces this.
