# ADR-0066: Nutrition resolution — cache first, width by method, and a gap that stays a gap

## Status
Accepted. Builds `migrations/0050_nutrition.sql` and `tools/engines/nutrition.py`; extends
`lib/egress.py` with the source-API path (B12; REQ-NUT §D/§E). Supersedes ADR-0056's plan for a
separate egress module — the one built by ADR-0063 is extended instead.

## Date
2026-09-09

## The number this subsystem exists to avoid

A single kcal figure. Text-only LLM recall carries **652 kcal MAE**; frontier vision runs
**~36% MAPE with systematic downward bias**. A point estimate is a lie about precision, and it
is a convincing one — it looks exactly like a measurement.

So every resolved value is an interval whose width is a function of **how the value was
obtained**, and the widths live in `config.nutrition_interval_widths` rather than in code.
RULE-00 forbids quietly editing a threshold; a width in a table is a visible data change with a
diff, while a width in code gets copied into a second place and then edited in one of them.

| method | low | high | why |
|---|---|---|---|
| `labelled` / `usda_branded` / `off_product` / `joe` | 0.90 | 1.10 | label legal tolerance |
| `weighed` | 0.90 | 1.10 | ADR-0005: weighing removes portion error, not composition error |
| `portion_table` / `usda_foundation` | 0.80 | 1.20 | generic composition, inferred portion |
| `photo_estimate` | **0.75** | **1.60** | REQ-NUT-039 — asymmetric, wider ABOVE |

The asymmetry is the part worth defending. A symmetric ±40% was considered and rejected: the
documented bias is systematic **under**-estimation, so a symmetric interval encodes the wrong
shape of error while reading as more careful than it is.

## Decisions

1. **RULE-09 is enforced by the shape of the function, not by discipline.** The model extracts
   a name and a quantity; `resolve_item` and `resolve_drink` convert those into numbers by
   deterministic lookup. Neither takes a kcal, a gram or a standard-drink count as an argument,
   so there is no path by which a model-produced number reaches an atom — a test asserts the
   absence of such a parameter rather than trusting the caller.

2. **Cache first, always.** A lookup done once is not repeated: it costs a request, it can
   fail, and the answer does not change. `foods_cache.raw` keeps the source payload so a later
   change of interpretation can be re-derived without re-fetching.

3. **Joe's own portion outranks every source, permanently** (RULE-10, §D.4). Once he has said
   what a portion is, nothing downstream re-guesses it.

4. **An unresolvable item is a row in `unresolved_items`, never a zero.** A zero is a claim
   that the item had no calories. Knowing a food's composition is not knowing its quantity, so
   a cached food with no serving size and no stated weight is *unresolved* rather than assigned
   an invented serving (REQ-NUT-040, RULE-06).

5. **A meal takes its widest item's method** (REQ-NUT-042). A meal is only as well known as its
   least well known item; taking the narrowest — or the commonest — would let a
   photo-estimated side dish disappear into a labelled main.

6. **An assumed input is visible as width.** For drinks, only a labelled volume against a label
   ABV may narrow toward a point; an assumed ABV or an estimated volume produces a
   non-degenerate interval (REQ-NUT-067) and `provenance = 'defaulted'` rather than
   `'extracted'` (REQ-NUT-066). An assumption that renders as a point is indistinguishable from
   a measurement.

7. **The constants are configured, not inlined.** `g_per_standard_drink` is 14 g and
   REQ-NUT-068 calls it a *provisional placeholder*; `ethanol_density_g_per_ml` is 0.789
   (ADR-0030). A number in a config row can be re-ruled; a number inlined in code gets copied.

## One outbound path, extended rather than duplicated

ADR-0056 planned `lib/egress.py` as B12's deliverable. It already exists — ADR-0063 built it
for Workers AI — so it gains `get_json` rather than acquiring a sibling. RULE-29 reserves
**one** outbound path and `validate_layout.py` enforces it on imports; a second module with its
own logging would be a second place for an unlogged call to appear.

What they share is the log. What they do not share is the budget: a USDA lookup costs no
neurons, so it does not touch `neuron_ledger`. The allowlist is a table
(`config.egress_allowlist`), so adding a destination is a visible data change reviewable on its
own rather than a line inside a diff about something else.

**The request body is never logged.** A nutrition query carries what Joe ate; a log that
reproduces it turns the audit trail into a second copy of the record it audits, in a table with
different access rules. The log records host, purpose, byte counts and elapsed time.

## What is not done

- **No source call has ever been made.** Every test injects an explicit transport. Nothing here
  proves USDA's or Open Food Facts' response shape, and `USDA_API_KEY` does not exist yet — it
  is a Joe action (api.data.gov, free).
- **The USDA and OFF parsers are not written.** What is built is the deterministic half: the
  cache, the widths, the precedence and the ABV path — which is where the numbers come from.
  Turning a source payload into a `nutrients_per_100g` row is the next piece, and it is the
  piece that needs a real response to write against.
- **Migration 0050 is not applied.** Dry-run verified in the full chain (432 statements).
- **`panel.py` does not yet sum nutrients** with interval propagation (§E.3), so nothing renders.
- **`foods_cache` is empty**, so every resolution today is `Unresolved` — which is correct
  behaviour and no use at all until the sources are wired.
