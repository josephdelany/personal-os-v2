# 03 — FINANCE / SPEND SUBSYSTEM — REQUIREMENTS (EARS)

Status: DRAFT v1. Author: Claude Code. Owner: Joe.
ID scheme: `REQ-FIN-nnn`. Every requirement is labelled with its EARS pattern.
Source research: `/home/claude/RESEARCH/D_FINANCE.md`. Superseded doctrine: `/home/claude/PERSONAL_OS_BUILD/08_LENS_CONTEXT.md` §3.

## §0 — DOCTRINAL PREAMBLE: WHAT CHANGED AND WHAT DID NOT

**The prohibition is overturned.** `08_LENS_CONTEXT.md` §3 said: *"Not a budget app. Nothing in this system tells Joe how to spend money, categorises his life into 'wants and needs,' or shows a pie chart."* Joe has overturned the first two clauses. His words:

> *"i want an app theat tracks my bank status, tracks my purhcases, orgnaizes my pruceases, can see what is necesary and not based on other data of usage, see where I spend the most, and teach me about my habits, like when i have a lot of work and im stressed i go to the bar and drink or I tend to withdraw and take a short break that turns long."*

So: a money surface exists. Purchases are organised. Concentration of spend is shown. Necessity is *inferred* (never asserted). Habits are surfaced.

**The restraint survives, and the research independently re-derives it from a direction Joe did not anticipate.** Pocheptsova Ghosh & Huang, five studies: participants given *precise, frequent* budget feedback **overspent by ~$40 (Field Study 1, n=283, p=.002) and $32.00 (Field Study 2, n=363)**. A *range* instead of an exact figure attenuated the effect (Lab Study 4, n=198). Splitting a budget into sub-categories **increased** total spend (Field Study 5, n=251). The mechanism is that certainty removes the safety margin.

The synthesis, and the governing sentence of this document:

> **The money surface exists. The nagging tally does not.**

Three further findings set the ceiling on how loudly this subsystem may speak:

- Personality-from-spend: best published AUROCs are **Materialism 0.588, Self-Control 0.585, Extraversion 0.573, Neuroticism 0.558** (Tovanich et al. 2021, n=1,306). Agreeableness, Conscientiousness and Openness performed so poorly they were dropped. 0.55–0.59 is near chance.
- The only published N=1 mood-vs-spend study (Nelson et al. 2022, bipolar II, 3,373 transactions, 24 months) returned **null**: frequency F(1,558)=0.35, p=.556; volume F(1,431)=0.19, p=.665.
- Zero-shot LLM transaction categorization scores **60.4%** against 91% for a trained weakly-supervised approach and 73.4% for a calibrated fine-tuned FinBERT.

Therefore the design principle inherited from the research verbatim: **the system's job is to notice and ask, not to conclude.**

### §0 requirements
```
**REQ-FIN-001** (Ubiquitous) The finance subsystem SHALL persist every transaction as an `atom` of kind 'transaction' in the shared atoms table, carrying `lane`, `confidence`, `source` and `provenance`, so that spend is queryable on the same `subject_day` (`atoms.local_date`) axis as every other lens.
**REQ-FIN-002** (Ubiquitous) The finance subsystem SHALL record, for every displayed number, the count of underlying observations (n) in the same view model as the number itself.
**REQ-FIN-003** (Unwanted behaviour) IF a rendering component would display a finance figure without an accompanying n, THEN the finance subsystem SHALL refuse to render the component and SHALL write a row to `render_violations` with the component name and the requirement ID 'REQ-FIN-002'.
**REQ-FIN-004** (Ubiquitous) The finance subsystem SHALL incur $0.00 in recurring monetary cost. No code path SHALL require a paid subscription, a metered API, or a credit-card-backed account to execute. ```


## §A — INGESTION

**The fact that governs this section:** there is no free, reliable, automated US bank transaction feed in 2026. The CFPB §1033 rule that would have banned banks from charging for data access is enjoined and under rewrite. JPMorgan Chase charges aggregators; Plaid signed a paid data deal with JPMorgan in Sept 2025. GoCardless/Nordigen is closed to new signups and was EU-only regardless. OFX Direct Connect is dead (Chase discontinued it 2022-10-06). Every mature open-source personal-finance project independently converged on "SimpleFIN plus a really good CSV importer."

So the architecture is three tiers, decoupled from analysis by one canonical table.

### A.1 Tier 1 — manual CSV/QFX import (the floor)
```
**REQ-FIN-010** (Ubiquitous) The ingest layer SHALL accept transaction files in CSV, OFX, QFX and QBO formats without any network call to a third party.
**REQ-FIN-011** (Event-driven) WHEN a file is delivered to the dedicated ingest mailbox or the Supabase Storage ingest bucket, the ingest layer SHALL compute a SHA-256 hash of the file bytes and SHALL insert one immutable row into `raw_documents` carrying the hash, the filename, the byte count and the receipt timestamp.
**REQ-FIN-012** (Unwanted behaviour) IF a delivered file's SHA-256 hash already exists in `raw_documents`, THEN the ingest layer SHALL skip parsing, SHALL increment `raw_documents.duplicate_delivery_count`, and SHALL NOT create any `raw_transactions` row.
**REQ-FIN-013** (Ubiquitous) The ingest layer SHALL parse OFX/QFX/QBO files using `ofxtools` and SHALL NOT use `ofxtools`' fetch/Direct-Connect client for any purpose.
**REQ-FIN-014** (Ubiquitous) The ingest layer SHALL resolve CSV column semantics from a per-institution YAML mapping file stored in the repository, one file per institution, and SHALL NOT infer column meaning heuristically at runtime.
**REQ-FIN-015** (Unwanted behaviour) IF a CSV file's header row does not match any institution mapping, THEN the ingest layer SHALL write the file reference to `raw_quarantine` with reason 'no_institution_mapping', SHALL create a review-queue row asking Joe to identify the institution, and SHALL NOT create any `raw_transactions` row.
**REQ-FIN-016** (Ubiquitous) The ingest layer SHALL support Apple Card, Venmo, PayPal and Cash App statement exports as first-class institution mappings, because P2P and wallet spend is the "went out with friends" signal that bank-level categorization renders as an opaque 'VENMO' descriptor.
**REQ-FIN-017** (Event-driven) WHEN 35 days have elapsed since the most recent successful Tier 1 import for a given account, the ingest layer SHALL emit exactly one reminder to Joe naming that account, and SHALL NOT emit a second reminder for that account until a successful import occurs. ```

### A.2 Tier 2 — Gmail alert and receipt parsing (the automation layer)

Gmail API is free at personal scale: 80,000,000 quota units/day free threshold, `messages.get` = 20 units. Two distinct sources with different value: **bank/card transaction alerts** arrive within seconds-to-minutes of the swipe and carry true time-of-day — which CSV exports discard and paid aggregators lag by ~24h — and **merchant order confirmations** carry line items, the only free source of item-level detail.
```
**REQ-FIN-020** (Ubiquitous) The email ingest job SHALL run on a GitHub Actions cron at an interval of 15 minutes and SHALL poll the Gmail API for messages in the ingest mailbox not yet present in `raw_documents`.
**REQ-FIN-021** (Event-driven) WHEN a bank or card transaction-alert email is parsed, the ingest layer SHALL create a `raw_transactions` row with `pending = true` and SHALL set `observed_at` to the timestamp carried in the alert body, or, where the body carries no timestamp, to the message's `Date` header.
**REQ-FIN-022** (Ubiquitous) The ingest layer SHALL treat the time-of-day carried by a transaction-alert email as the authoritative value for `occurred_at` and SHALL NOT allow a later-arriving CSV or API observation of the same purchase to overwrite it.
**REQ-FIN-023** (Event-driven) WHEN a merchant order-confirmation email is parsed, the ingest layer SHALL create one `transaction_items` row per line item, each carrying description, quantity and unit amount, linked to the canonical transaction by foreign key.
**REQ-FIN-024** (Ubiquitous) The email ingest layer SHALL attempt parsing with a per-sender deterministic template (regex or BeautifulSoup selector set) before invoking any model.
**REQ-FIN-025** (Unwanted behaviour) IF no per-sender template matches an email from a sender previously parsed successfully, THEN the ingest layer SHALL write a row to `parse_failures` with the sender, the message ID and the template version, and SHALL notify Joe once per sender per 7-day window that the format has drifted.
**REQ-FIN-026** (Optional feature) WHERE the Cloudflare Workers AI fallback is enabled, the ingest layer SHALL invoke it only for emails that failed template parsing, and SHALL mark any resulting `raw_transactions` row `lane = 'inferred'` with `confidence` set to the model's reported value.
**REQ-FIN-027** (Unwanted behaviour) IF the Cloudflare Workers AI free daily allowance (10,000 Neurons, resetting 00:00 UTC) is exhausted, THEN the ingest layer SHALL record the parse as deferred, SHALL retry after the next UTC reset, and SHALL NOT fall back to any billable inference endpoint.
**REQ-FIN-028** (Ubiquitous) The ingest layer SHALL flag every alert-derived amount as a pre-authorisation estimate until a posted observation supersedes it, because a $50 bar pre-auth commonly settles at $67 after tip. ```

### A.3 Tier 3 — API adapter (optional, pluggable)
```
**REQ-FIN-030** (Ubiquitous) The ingest layer SHALL expose every source behind a single interface `fetch_transactions(account, since) -> list[RawTxn]`, and no code downstream of `raw_transactions` SHALL reference a provider name.
**REQ-FIN-031** (Optional feature) WHERE the Teller.io adapter is enabled, the ingest layer SHALL authenticate using mTLS client certificates read from a GitHub Actions secret and SHALL operate against the Teller Development environment (real bank data, free, capped at 100 enrollments).
**REQ-FIN-032** (Unwanted behaviour) IF the Teller.io adapter returns an authentication, quota or tier-reclassification error, THEN the ingest layer SHALL disable the adapter, SHALL notify Joe once, and SHALL continue Tier 1 and Tier 2 ingest with no degradation of any downstream function.
**REQ-FIN-033** (Ubiquitous) The finance subsystem SHALL remain fully functional — ingest, categorization, recurrence detection, usage inference and review — with every Tier 3 adapter disabled.
**REQ-FIN-034** (Ubiquitous) The ingest layer SHALL NOT store bank login credentials, and SHALL NOT drive a headless browser against any financial institution. ```

### A.4 Dedupe and the two-timestamp rule

The same purchase arrives up to three times: alert → API pending → CSV posted.
```
**REQ-FIN-040** (Ubiquitous) The `transactions` table SHALL carry `occurred_at` and `posted_at` as two distinct columns. `occurred_at` is the best available moment of the swipe; `posted_at` is the settlement date.
**REQ-FIN-041** (Ubiquitous) The behavioural analysis layer SHALL read `occurred_at` and SHALL NOT read `posted_at`. The reconciliation and balance layer SHALL read `posted_at` and SHALL NOT read `occurred_at`.
**REQ-FIN-042** (Unwanted behaviour) IF a code path would write the same value to both `occurred_at` and `posted_at` where a distinct swipe timestamp was available from any source, THEN the ingest layer SHALL reject the write and SHALL log the rejection with the source ID.
**REQ-FIN-043** (Event-driven) WHEN a new `raw_transactions` row is created, the dedupe engine SHALL search for a candidate match on the key (account, amount within 25%, date within 3 days, normalized merchant equal).
**REQ-FIN-044** (Event-driven) WHEN a candidate match is found, the dedupe engine SHALL append the new source to the canonical transaction's `sources[]` array and SHALL NOT create a second canonical transaction.
**REQ-FIN-045** (Event-driven) WHEN a posted observation supersedes a pending observation of the same canonical transaction, the dedupe engine SHALL overwrite `amount` and `posted_at` from the posted observation and SHALL preserve `occurred_at` from the earliest observation.
**REQ-FIN-046** (Ubiquitous) The amount tolerance in REQ-FIN-043 SHALL be 25% of the pending amount, chosen to absorb a tip; the dedupe engine SHALL record the observed delta in `transactions.tip_delta` for later calibration.
**REQ-FIN-047** (Unwanted behaviour) IF two or more canonical transactions match a single incoming observation, THEN the dedupe engine SHALL create a `review_queue` row with status 'ambiguous_dedupe', SHALL attach all candidate IDs, and SHALL NOT merge anything.
**REQ-FIN-048** (Ubiquitous) The dedupe engine SHALL NEVER merge two canonical transactions that carry a recorded 'not_same' adjudication from Joe.
**REQ-FIN-049** (Event-driven) WHEN a transaction is identified as an inbound P2P receipt (Venmo, Cash App, PayPal, Zelle) within 72 hours of an outbound transaction at a bar or restaurant merchant, the ingest layer SHALL write a row to `transfers` linking the two and SHALL NOT delete either.
**REQ-FIN-050** (Ubiquitous) Any metric describing spend at a bar, restaurant or liquor merchant SHALL be computed net of linked inbound `transfers`, and SHALL display the netted amount alongside the gross.
**REQ-FIN-051** (Event-driven) WHEN an ATM withdrawal transaction is ingested, the finance subsystem SHALL label it 'destination unknown' in every surface on which it appears and SHALL exclude its amount from every category rollup. ```


### A. NON-GOALS

- Real-time balance display. The best free path (alert email) gives transactions, not balances; Tier 1 gives balances monthly at best.
- Investment/portfolio tracking. Wrong subsystem; Ghostfolio's problem, not this one.
- Multi-user, household, or shared-account ledgers. n=1, permanently.
- Screen scraping of any financial institution. Explicitly rejected on security and ToS grounds — storing bank credentials in a CI secret to drive a headless browser is a materially worse posture than every alternative, and MFA makes it structurally unreliable regardless.
- Historical backfill beyond what the institution's own export UI offers.
- Automatic reconciliation to the cent against a bank-reported balance. Cash spend makes this unachievable (§C).

### A. ALTERNATIVES CONSIDERED

| Path | Cost | Verdict |
|---|---|---|
| Manual CSV/QFX + good importer | $0 | **Adopted as Tier 1.** Never breaks, no third party ever holds the data, ~10–20 min/month of Joe's time. |
| Gmail alert + receipt parsing | $0 | **Adopted as Tier 2.** Only free source of true time-of-day and of line items. Format drift is the accepted cost. |
| Teller.io Development environment | $0, 100 enrollments | **Adopted as optional Tier 3.** Real bank data, free. Honest caveat: "Development" is a development environment; using it as permanent personal production is within the letter of the docs but is not a promise of forever. Medium longevity risk. |
| Plaid Trial (10 Production Items) | $0 | Rejected as primary; permitted as a fallback adapter. Explicitly a trial posture, Plaid now pays JPMorgan per call, and Plaid holds a copy of the data — direct conflict with "Joe owns the data." |
| **SimpleFIN Bridge** | **$15/yr ($1.50/mo)** | **THE ONE CONSIDERED RULE-BREAK, RECORDED HERE AND NOWHERE ELSE.** Best product in the space, built for individuals rather than fintechs, the one thing every serious open-source project settled on. Covers 25 institutions and 25 apps; pulls at most 90 days of history; updates roughly once per 24 hours. It violates the $0-recurring constraint, which Joe has stated twice as hard. Per REQ-FIN-004 and REQ-FIN-030, **no code path may require it**; it may only ever arrive as a drop-in adapter behind the existing interface if Joe explicitly reverses the constraint in writing. |
| GoCardless / Nordigen, Enable Banking, open-banking.io | n/a | Ruled out. Signups disabled / discontinued, and EU-PSD2-only regardless — never a US path. |
| MX, Finicity, Yodlee, Akoya | enterprise | Ruled out. Sales-led, KYB, minimum commitments, no self-serve personal tier. |
| OFX Direct Connect | $0–$120/yr | Ruled out. Effectively dead in the US; Chase discontinued 2022-10-06; where it survives it is paid (BofA $9.95/mo, U.S. Bank $3.95/mo). `ofxtools` retained as a *parser* only. |
| Screen scraping (`mintapi`, `finance-dl`) | $0 | **Recommended against and forbidden by REQ-FIN-034.** |

### A. UNRESOLVED QUESTIONS

- **Which institutions does Joe actually bank with?** The set of per-institution YAML mappings (REQ-FIN-014) cannot be written without it, and Teller/Plaid viability is institution-dependent.
- **Does every one of Joe's institutions offer per-transaction email alerts?** The research confirms most major US banks do, but not universally; cash withdrawals and ACH often do not alert at all. Coverage is unknown until enumerated.
- **What is the correct dedupe amount tolerance?** REQ-FIN-046 sets 25% as a placeholder to absorb a tip. No published figure exists for pre-auth-to-settle delta distribution. `transactions.tip_delta` is instrumented specifically so this number can be replaced with a measured one after ~3 months.
- **What is the correct dedupe date window?** ±3 days is taken from the research's suggested key; it is not empirically derived.
- **Does the Gmail free daily threshold survive Google's May 2026 standardized Workspace API pricing indefinitely?** Usage within the threshold incurs no charge and Google commits to 90 days' notice, so the residual risk is low but non-zero.
- **How is the ingest mailbox secured?** OAuth refresh-token storage and rotation policy is not specified here and belongs in the security spec.
- **What fraction of Joe's spend is cash?** Unknown, and it bounds the credibility of every drinking-related metric (§C, §D).

## §B — MERCHANT AND CATEGORY RESOLUTION

Bank descriptors are garbage by design: `SQ *COFFEE 8005551212 CA` is Square's payment-facilitator prefix, plus a merchant-chosen DBA string, plus Square's support phone number, plus a state code. The right model is **entity resolution against a canonical merchant table Joe owns**, not text cleaning.

The cascade below is ordered by cost and by trustworthiness. The critical structural fact: **zero-shot LLM categorization scores 60.4%**, against 91% balanced accuracy for a trained weakly-supervised approach and ~95% for embeddings-plus-small-classifier on ~100 labelled examples. The LLM is therefore the *last* move, not the first, and it is gated behind confidence. Personal spending is extremely long-tailed — Joe has on the order of 200–400 distinct merchants — which is why n=1 personalization beats any general model.

### B.1 Descriptor normalization
```
**REQ-FIN-060** (Event-driven) WHEN a `raw_transactions` row is created, the normalizer SHALL produce a `normalized_descriptor` by stripping known payment-facilitator prefixes (at minimum `SQ *`, `TST*`, `PYPL*`, `SP `), phone numbers, trailing city and two-letter state codes, store numbers and digit runs, and by upper-casing the remainder.
**REQ-FIN-061** (Ubiquitous) The normalizer SHALL preserve the original descriptor verbatim in `raw_transactions.raw_descriptor` and SHALL NOT overwrite it.
**REQ-FIN-062** (Ubiquitous) The normalizer SHALL store the ordered list of stripping rules that fired, by rule ID, in `transactions.provenance.normalization_rules`. ```

### B.2 The merchant resolution cascade
```
**REQ-FIN-070** (Event-driven) WHEN a normalized descriptor exactly matches an existing row in `merchant_patterns`, the resolver SHALL assign that merchant, SHALL set `merchant_source = 'pattern_exact'` and `confidence = 1.0`, and SHALL NOT invoke any later cascade step.
**REQ-FIN-071** (Event-driven) WHEN no exact pattern match exists, the resolver SHALL evaluate the regex patterns in `merchant_patterns` in descending specificity order and SHALL assign the first match with `merchant_source = 'pattern_regex'`.
**REQ-FIN-072** (Event-driven) WHEN no regex pattern matches, the resolver SHALL compute a `difflib.SequenceMatcher` ratio against every known merchant name and SHALL assign the top match only where the ratio is greater than or equal to 0.80, with `merchant_source = 'fuzzy'` and `confidence` set to the ratio.
**REQ-FIN-073** (Unwanted behaviour) IF the top fuzzy ratio is below 0.80, THEN the resolver SHALL create a new provisional merchant flagged `unconfirmed`, SHALL create a `review_queue` row for Joe's confirmation, and SHALL NOT write the provisional merchant into `merchant_patterns`.
**REQ-FIN-074** (Event-driven) WHEN Joe confirms a provisional merchant, the resolver SHALL insert the normalized descriptor into `merchant_patterns` bound to that merchant. ```

### B.3 The categorization cascade
```
**REQ-FIN-080** (Ubiquitous) The categorizer SHALL execute the following layers in order, and each layer SHALL run only if every preceding layer abstained: (1) descriptor-hash memory, (2) merchant-entity category, (3) MCC prior, (4) pgvector kNN over Joe's own corrected history, (5) confidence-gated LLM, (6) ask Joe.
**REQ-FIN-081** (Ubiquitous) The categorizer SHALL write `category_source` and `confidence` on every categorization, where `category_source` is one of {'hash','merchant','mcc','knn','llm','user'}.
**REQ-FIN-082** (Event-driven) WHEN the normalized descriptor hash has been seen before with a Joe-confirmed category, the categorizer SHALL reuse that category with `confidence = 1.0` and SHALL NOT invoke any later layer.
**REQ-FIN-083** (Ubiquitous) The categorizer SHALL treat an MCC value as a weak prior with a maximum contributed confidence of 0.60, and SHALL NEVER treat MCC as ground truth, because the same business codes differently across cards and departments, and because MCC 5812 (Eating Places) versus 5813 (Drinking Places) is set by the acquirer — the exact distinction on which any alcohol analysis depends.
**REQ-FIN-084** (Ubiquitous) The categorizer SHALL operate correctly when MCC is absent, because MCC is absent from CSV exports, from alert emails and from OFX.
**REQ-FIN-085** (Event-driven) WHEN the kNN layer runs, the categorizer SHALL embed the normalized descriptor, SHALL retrieve the k=5 nearest neighbours from `category_embeddings` by cosine distance, and SHALL assign the plurality category with `confidence` set to the winning vote fraction.
**REQ-FIN-086** (Ubiquitous) The `category_embeddings` table SHALL contain only descriptors that Joe has confirmed or corrected, and SHALL NEVER contain a descriptor labelled by the LLM layer alone.
**REQ-FIN-087** (State-driven) WHILE fewer than 100 confirmed labelled examples exist in `category_embeddings`, the categorizer SHALL route every kNN result to the review queue rather than auto-applying it, because the ~95% accuracy figure for embeddings-plus-classifier is reported at roughly 100 labelled examples and is not claimed below that.
**REQ-FIN-088** (Event-driven) WHEN the LLM fallback layer runs, the categorizer SHALL supply the complete category taxonomy in the prompt and SHALL request a confidence value with the label.
**REQ-FIN-089** (Ubiquitous) The categorizer SHALL auto-apply an LLM-produced category only where the reported confidence is greater than or equal to 0.80, mirroring the published finding that >0.8-confidence predictions were 90.4% accurate while the same model's overall zero-shot accuracy was 60.4%.
**REQ-FIN-090** (Unwanted behaviour) IF an LLM-produced confidence is below 0.80, THEN the categorizer SHALL leave the transaction uncategorized, SHALL create a `review_queue` row, and SHALL NOT display a guessed category anywhere in the UI.
**REQ-FIN-091** (Ubiquitous) The categorizer SHALL NEVER invoke the LLM layer as the first move for any transaction.
**REQ-FIN-092** (Ubiquitous) The LLM prompt SHALL contain the normalized descriptor, the amount, the MCC where present and the taxonomy, and SHALL NOT contain any location coordinate, any mood value, or any other lens's data.
**REQ-FIN-093** (Ubiquitous) The category taxonomy SHALL contain no more than 25 leaves, because fragmenting spend into many sub-categories increased total spending in Field Study 5 (n=251). ```

### B.4 The correction loop — Joe outranks everything, permanently
```
**REQ-FIN-100** (Event-driven) WHEN Joe assigns or corrects a category on a transaction, the categorizer SHALL set `category_source = 'user'` and `confidence = 1.0` and SHALL stamp `corrected_at`.
**REQ-FIN-101** (Ubiquitous) The categorizer SHALL NEVER overwrite a category whose `category_source` is 'user'. No automated layer, no model retrain, no reprocessing job, and no schema migration SHALL change such a value.
**REQ-FIN-102** (Event-driven) WHEN Joe corrects a category, the categorizer SHALL write the correction back to all three memories in the same transaction: the descriptor-hash table, the merchant's default category, and `category_embeddings`.
**REQ-FIN-103** (Event-driven) WHEN Joe corrects a category, the categorizer SHALL re-evaluate every existing uncorrected transaction sharing that normalized descriptor hash and SHALL apply the corrected category to each, recording `category_source = 'user_propagated'`.
**REQ-FIN-104** (Ubiquitous) The categorizer SHALL maintain a per-layer accuracy tally, computed as the fraction of that layer's auto-applied categories that Joe subsequently corrected, and SHALL make it queryable so the failing layer is identifiable.
**REQ-FIN-105** (Unwanted behaviour) IF any layer's correction rate exceeds 20% over its most recent 50 auto-applied categorizations, THEN the categorizer SHALL stop auto-applying that layer, SHALL route it to the review queue instead, and SHALL notify Joe once.
**REQ-FIN-106** (Ubiquitous) The review queue SHALL present at most 20 items per session and SHALL order them by descending absolute amount, so that a review session is bounded in time. ```

### B. NON-GOALS

- A general-purpose merchant-cleaning engine. Joe has 200–400 distinct merchants and a long tail; a descriptor-prefix hash plus manual confirmation covers >95% of volume after two months. Solving the general problem is wasted work.
- Purchasing commercial enrichment (Plaid Enrich, Tapix, Context.dev, Zafin). All paid; violates REQ-FIN-004.
- Training a model from scratch (Rel-Cat's `Txn-Bert` approach). Requires a relational corpus across many customers that does not exist at n=1.
- Hierarchical or deeply nested categories. REQ-FIN-093 caps the taxonomy at 25 leaves for behavioural reasons, not technical ones.
- Automatic merchant merging without confirmation. Actual Budget's payee merging is deliberately manual; that is the correct choice here too.

### B. ALTERNATIVES CONSIDERED

- **spaCy NER layer for brand extraction** (the published three-layer engine's third layer, trained on ~1,000 annotations over 50 iterations). Considered and deferred: no quantitative accuracy was published for it, and at n=1 the pattern table subsumes most of its value. Revisit only if the fuzzy-match abstention rate exceeds 10% after 3 months.
- **Zero-shot LLM as primary categorizer.** Rejected on evidence: 60.4% vs 73.4% for calibrated FinBERT-FT and 91% balanced accuracy for the weakly-supervised approach. Convenient, not accurate.
- **Fine-tuning a classifier.** The OpenAI cookbook result (0.95 weighted accuracy on 101 labelled transactions, 5 classes) suggests this is viable, but kNN over pgvector reaches comparable quality with zero training infrastructure, updates instantly on correction, and is $0 on Supabase. kNN adopted.
- **Amount and timing as classifier features.** The weak-supervision paper's dual-GRU over the *time series* of amounts matters a great deal for rent, utilities and subscriptions. Not adopted in the categorizer; the recurrence engine (§C) captures the same information more legibly.
- **Rules engine only** (the Actual Budget / Firefly III approach: conditions → actions plus per-payee category memory). This is genuinely what shipping products do — "it learns after you correct it a few times" is payee memory plus a base classifier. Adopted as layers 1 and 2, not as the whole system.

### B. UNRESOLVED QUESTIONS

- **What is Joe's actual taxonomy?** 25 leaves is a cap, not a list. The leaves must be chosen with him, and the choice interacts with §E's restraint rules.
- **Which embedding model, at what dimensionality?** The research establishes that Cloudflare Workers AI can host one at $0 but names no specific model and reports no performance on abbreviated financial descriptors — and the Rel-Cat paper explicitly warns that generic pretrained encoders underperform on descriptors, which "adhere to formatting standards set by financial institutions" rather than natural language.
- **Is k=5 correct for the kNN vote?** No basis in the research; a conventional default. Needs tuning against Joe's own correction log.
- **Is 0.80 the right fuzzy-match threshold?** The research suggests "~0.8" without derivation.
- **The 20% / 50-item circuit breaker in REQ-FIN-105 has no empirical basis.** It is a guess at a reasonable stop-loss.
- **How is a single transaction spanning two categories handled** — a Target run that is 60% groceries and 40% electronics? Line items (REQ-FIN-023) solve it where a receipt email exists, and nowhere else.

## §C — NECESSITY INFERENCE

**This is the most dangerous section in the file, and it is written defensively on purpose.**

Joe asked the system to "see what is necessary and not based on other data of usage." The research's reframe is that "necessary" is three different questions, and conflating them is why no product does this well:

1. **Was it used?** — empirically answerable with cross-modal data.
2. **Was it worth it?** — only Joe can answer; the system can ask and remember.
3. **Was it needed?** — a values judgment. The system must never assert it. Rent is necessary; a $6 coffee might be the thing that made a bad Tuesday survivable.

**Build #1. Prompt for #2. Never claim #3.** The UI vocabulary is therefore **used / unused / unknown**, never necessary / unnecessary.

The reason for the restraint is not squeamishness, it is measurement error. Personality-from-spend AUROCs are 0.55–0.59 — near chance — and three of the Big Five performed so badly they were dropped from the analysis. A system that infers *values* from spend when the literature cannot reliably infer *traits* from spend is making a claim its data cannot support.

What the evidence *does* support is precise and financially material: DellaVigna & Malmendier found gym members waited a mean of **2.31 months after their final visit before cancelling**, burning ~**$187**; 20% waited over four months; members overpaid ~$614 per membership spell, 43% of their $1,423 total spend. Einav, Klopack & Mahoney found consumer inattention raises firm revenues by **14% to over 200%**, and that at the 12-month card-expiry forced-attention point, retention drops from **~75% to ~52%**. Closing a measured 2.31-month, $187 gap is a defensible, non-moralising win. Telling Joe his coffee is unnecessary is not.

### C.1 Necessity is a tier, not a fact
```
**REQ-FIN-110** (Ubiquitous) The finance subsystem SHALL represent usage status as one of exactly three tiers — 'used', 'unused', 'unknown' — and SHALL NOT represent it as a boolean, a score, or a percentage.
**REQ-FIN-111** (Ubiquitous) The finance subsystem SHALL default every purchase's usage status to 'unknown' and SHALL change it only on the arrival of an explicit evidence row in `usage_evidence` or an explicit statement from Joe.
**REQ-FIN-112** (Ubiquitous) The finance subsystem SHALL NEVER write, store, display or export the words 'necessary', 'unnecessary', 'needed', 'wasteful' or 'frivolous' in reference to any transaction, merchant or category.
**REQ-FIN-113** (Ubiquitous) Every usage status displayed SHALL be accompanied by the evidence that produced it, named in concrete terms — for example "last gym `place_visit` 71 days ago" — and SHALL NOT be displayed as a bare label.
**REQ-FIN-114** (Ubiquitous) Every usage status SHALL carry `lane = 'inferred'` and a `confidence` value unless it was set directly by Joe, in which case it SHALL carry `lane = 'hard'` and `confidence = 1.0`.
**REQ-FIN-115** (Event-driven) WHEN Joe overrides a usage status, the finance subsystem SHALL persist the override and SHALL NEVER allow any automated process to change it.
**REQ-FIN-116** (Ubiquitous) Where a quantity is inferred rather than observed, the finance subsystem SHALL express it as an interval and SHALL NOT express it as a point estimate. ```

### C.2 What is inferable, and what is not

The research ranks inference quality by purchase type. This ranking is binding: the system's confidence is capped by the row it falls in.

| Purchase type | Usage evidence available | Inference quality |
|---|---|---|
| Gym / studio / climbing membership | `place_visit` inside the venue geofence | **Strong** — the DellaVigna case exactly |
| Streaming subscription | Spotify recently-played, Trakt/Plex/Jellyfin history, Last.fm scrobbles | **Strong where an API exists.** Netflix and Hulu have none. |
| Software / SaaS | app usage on device; "new sign-in to X" emails | **Medium** — login emails are a good free proxy |
| Groceries | logged meals, calorie logs, weight trend | **Weak-medium** — the FoodAPS energy-gap method is noisy at n=1 and confounded by eating out |
| Restaurant / bar | consumed by definition | **N/A** — the question is *why* (§D), not whether |
| Physical goods (Amazon) | nothing automatic; refund transactions are a partial signal | **Weak** — requires Joe to say |
| Transport / rideshare | location traces confirm the trip | **Strong but trivially so** |
| Clothing | nothing | **Not inferable. Say so.** |
```
**REQ-FIN-120** (Ubiquitous) The usage-inference engine SHALL cap the confidence of any inferred usage status at the value assigned to its purchase type in the table above: strong = 0.90, medium = 0.60, weak = 0.30, not-inferable = 0.00.
**REQ-FIN-121** (Unwanted behaviour) IF a purchase falls in the 'not inferable' class, THEN the finance subsystem SHALL display the status 'unknown', SHALL display the text "no usage signal exists for this", and SHALL NOT attempt any inference.
**REQ-FIN-122** (Ubiquitous) The grocery-versus-consumption gap SHALL be reported as a range with a stated uncertainty and SHALL NEVER be reported as a point estimate, because the published method infers waste as the gap between food energy acquired and metabolic energy required, and that gap is confounded at n=1 by eating out.
**REQ-FIN-123** (Optional feature) WHERE a merchant has a known physical location, the usage-inference engine SHALL treat the transaction itself as a location fix and SHALL record it as `usage_evidence` of type 'transaction_as_visit'. ```

### C.3 Recurrence detection — the substrate for the whole section
```
**REQ-FIN-130** (Ubiquitous) The recurrence engine SHALL group candidate streams by (canonical_merchant, account) and SHALL require at least 3 occurrences before marking a stream 'mature'.
**REQ-FIN-131** (Ubiquitous) The recurrence engine SHALL emit an 'early_detection' stream at 2 occurrences, marked as such, so that a newly-started subscription is visible before it has run three cycles.
**REQ-FIN-132** (Ubiquitous) The recurrence engine SHALL test candidate periods of 7, 14, 15, 30, 91 and 365 days, and SHALL match the monthly hypothesis using same-day-of-month plus or minus 3 days rather than a fixed 30-day interval, so that weekend and holiday shifts do not break the fit.
**REQ-FIN-133** (Ubiquitous) The recurrence engine SHALL use median interval and median absolute deviation, and SHALL NOT use mean and standard deviation, so that one missed month does not destroy the fit.
**REQ-FIN-134** (Ubiquitous) The recurrence engine SHALL classify each stream's amount behaviour as 'fixed' where the coefficient of variation is below 2%, 'fixed_with_step' where a changepoint is detected in the amount series, or 'variable' otherwise.
**REQ-FIN-135** (Event-driven) WHEN a changepoint is detected in a stream's amount series, the recurrence engine SHALL create an `insights` row stating the previous amount, the new amount and the month of the change.
**REQ-FIN-136** (Ubiquitous) The recurrence engine SHALL NOT require amount stability to classify a stream as recurring; strong periodicity with a consistent merchant SHALL be sufficient, so that utilities and phone bills are detected.
**REQ-FIN-137** (Ubiquitous) The recurrence engine SHALL mark a stream 'active' while days_since_last is below expected_period × 1.5 plus tolerance, 'lapsed' between 1.5× and 2.5×, and 'cancelled' beyond 2.5×.
**REQ-FIN-138** (Ubiquitous) The recurrence engine SHALL NEVER delete a lapsed or cancelled stream, because a resurrected stream is itself behavioural data.
**REQ-FIN-139** (Ubiquitous) The recurrence engine SHALL exclude groceries, fuel, coffee and bars from subscription detection, and SHALL route those merchants to the habit-rhythm engine (§D) instead — same mathematics, different table, different surface.
**REQ-FIN-140** (Event-driven) WHEN Joe marks a detected stream 'not a subscription' or reports a missed one, the recurrence engine SHALL persist the label and SHALL apply it in every subsequent run. ```

### C.4 The interventions that the evidence actually supports
```
**REQ-FIN-150** (Event-driven) WHEN an active recurring stream has zero rows in `usage_evidence` for 60 consecutive days, the finance subsystem SHALL schedule an insight for delivery on the stream's next expected charge date.
**REQ-FIN-151** (Ubiquitous) The finance subsystem SHALL time every unused-purchase insight to the renewal date rather than to the date of detection, because payment depreciation erodes the salience of a sunk cost over time and the renewal moment is when that salience is restored.
**REQ-FIN-152** (Ubiquitous) The finance subsystem SHALL run a synthetic renewal review exactly twice per calendar year, presenting every active recurring stream with its last-usage evidence and requiring an explicit keep-or-cancel response for each.
**REQ-FIN-153** (Ubiquitous) The synthetic renewal review SHALL be the only surface in the finance subsystem that requires a response from Joe on more than 10 items at once.
**REQ-FIN-154** (Event-driven) WHEN two or more active recurring streams resolve to merchants sharing the same service class (for example three music subscriptions or two cloud-storage plans), the finance subsystem SHALL surface the set as a duplicate-service observation with the combined monthly amount.
**REQ-FIN-155** (Event-driven) WHEN a recurring stream remains active while its associated login, app-usage or email activity has been absent for 90 days, the finance subsystem SHALL surface it as a zombie-stream observation naming the specific absent signal.
**REQ-FIN-156** (Event-driven) WHEN Joe cancels a stream as a result of any insight, the finance subsystem SHALL record the cancellation, the monthly amount and the originating insight ID, and SHALL include the running total of cancellations in the periodic review.
**REQ-FIN-157** (Ubiquitous) Every unused-purchase insight SHALL end in a question that Joe can answer, dismiss, or mark 'not useful'.
**REQ-FIN-158** (Event-driven) WHEN Joe marks an insight class 'not useful', the finance subsystem SHALL suppress every future insight of that class permanently and SHALL NOT re-raise it under a different wording. ```

### C. NON-GOALS

- Any assertion that a purchase was needed, or not needed. This is the section's central prohibition and it survives the doctrinal overturn intact.
- Any "wants vs needs" split, in the schema, the analysis or the UI.
- Any total labelled "unnecessary spending: $X". The research names this exact string as the anti-pattern.
- Inferring whether a purchase was *worth it*. No sensor measures satisfaction. The system may only ask and remember.
- Inferring usage of physical goods or clothing. Not inferable in a $0 system without object-level tracking that does not exist; REQ-FIN-121 requires the system to say so.
- A "financial health score", or any single-number summary of Joe's spending quality.
- Cancelling anything on Joe's behalf.

### C. ALTERNATIVES CONSIDERED

- **Continuous necessity score (0–1) per transaction.** Rejected. A continuous score invites ranking, ranking invites a leaderboard of shameful purchases, and the underlying inference is not precise enough to support one digit of resolution, let alone two. Three tiers (REQ-FIN-110) is the honest resolution.
- **Binary used/unused.** Rejected. It forces the enormous 'unknown' mass into one of the two answers, and 'unknown' is the truthful answer for most of Joe's spend.
- **Inferring necessity from category** (rent = necessary, bars = not). Rejected: this is exactly the moralising taxonomy the doctrine forbids, dressed as a lookup table.
- **Inferring necessity from personality-adjacent models.** Rejected on the AUROC evidence (0.55–0.59, three traits undroppable-to-droppable). If traits cannot be read from spend, values certainly cannot.
- **Subaio-style cluster analysis over frequency, amount and merchant**, with its claimed 98.7% accuracy and 0.044 false-positive rate. The claim is vendor marketing with no published methodology, no denominator and no peer review; the method itself (clustering on those three axes) is sound and is essentially what §C.3 specifies.
- **Lomb-Scargle periodogram for subscription cadence.** Overkill for streams that are by definition regular; retained for §D's irregular habit series only.
- **Reporting the grocery-waste figure against the 31.9% national household average** ($1,866/household/year). Rejected as a comparison: a population mean is not a personal benchmark, and displaying it converts a measurement into a judgment.

### C. UNRESOLVED QUESTIONS

- **Is 60 days the right unused threshold (REQ-FIN-150)?** DellaVigna & Malmendier measured a 2.31-month mean gap between last visit and cancellation, which motivates a threshold in this neighbourhood, but the study measured behaviour, not the optimal intervention point. Untested.
- **Is 90 days right for zombie-stream detection (REQ-FIN-155)?** No basis in the research. A guess.
- **Which usage-evidence sources will actually exist for Joe?** Spotify has an API; Netflix and Hulu do not. Whether Joe runs a location logger at all determines whether the strongest inference class (gym) is available at all.
- **The confidence caps in REQ-FIN-120 (0.90 / 0.60 / 0.30 / 0.00) are assigned, not derived.** The research ranks inference quality ordinally as strong/medium/weak; the numbers are this document's translation of that ordinal ranking and should be treated as placeholders.
- **What happens when the same merchant supports two streams** — Amazon Prime annual and Prime Video monthly? REQ-FIN-130 permits sub-splitting by amount cluster; the splitting criterion is unspecified.
- **How should a shared subscription be handled** — Joe pays, someone else uses it? Usage evidence from Joe's lenses will read 'unused' and be wrong.
- **Does the twice-yearly ritual (REQ-FIN-152) actually work at n=1?** The 75%→52% retention drop was measured at involuntary card expiry across many consumers. A self-imposed ritual is not involuntary, and the effect may not transfer.

## §D — HABIT TEACHING AND CROSS-LENS LINKAGE

Joe's example: *"when i have a lot of work and im stressed i go to the bar and drink."* That is a four-atom chain on one `subject_day`: a work/calendar atom, a mood atom, a `transaction` atom at a bar merchant, and a `consume` atom with `props.class='alcohol'`. Optionally a fifth: a `place_visit` atom at the bar's geofence.

This is buildable. What is not buildable is the conclusion. The only published N=1 mood-versus-spend study — 24 monthly statements, 3,373 transactions, mood labelled retrospectively by the NIMH Life-Chart Method — found **nothing statistically significant**: frequency F(1,558)=0.35, p=.556; volume F(1,431)=0.19, p=.665; burstiness no significant difference. Only the qualitative visual analysis showed anything. That is the honest baseline, and any dashboard announcing "your spending indicates a low mood episode" is doing something the published literature could not do.

Two further constraints fall out of the research. First, **dollars are not drinks**: no study reports a clean correlation between individual alcohol expenditure and validated consumption, and six specific mechanisms break the mapping (price variance — $60 is 4 cocktails or 20+ liquor-store drinks; rounds and splitting; bar tabs including food; cash; pre-auth versus settled amount; someone else paying). So the system counts **visits and occasions, not dollars and not drinks**. Second, the mechanism Joe describes is not pathology: Rick, Pereira & Burson found that making purchase decisions genuinely reduces residual sadness by restoring a sense of personal control, and that the effect is emotion-specific — it works for sadness, not anger. Retail therapy in this literature *works*. The tone must reflect that.

### D.1 The link object
```
**REQ-FIN-160** (Ubiquitous) The finance subsystem SHALL express every cross-lens relationship as a row in `cooccurrences` carrying the participating atom IDs, the shared `subject_day`, the evidence tier, and the observation count n.
**REQ-FIN-161** (Event-driven) WHEN a `transaction` atom resolves to a merchant of category 'bar' or 'restaurant', the linkage engine SHALL search for `consume` atoms with `props.class='alcohol'` within ±3 hours of `occurred_at`, for `mood` atoms on the same `subject_day`, and for `place_visit` atoms overlapping `occurred_at`.
**REQ-FIN-162** (Ubiquitous) The linkage engine SHALL join on `occurred_at`, never on `posted_at`, because the settlement date is commonly the following day and would attribute a Thursday night to Friday.
**REQ-FIN-163** (Unwanted behaviour) IF a transaction's `occurred_at` was derived from a CSV import with no time-of-day component, THEN the linkage engine SHALL mark the resulting co-occurrence 'date_only', SHALL NOT use it in any within-day analysis, and SHALL NOT count it toward any hour-of-day pattern.
**REQ-FIN-164** (Event-driven) WHEN a bar or restaurant transaction exists on a `subject_day` with no alcohol `consume` atom within ±3 hours, the finance subsystem SHALL create one dismissible prompt asking Joe to log the drinks, SHALL offer it once, and SHALL NOT repeat it.
**REQ-FIN-165** (Ubiquitous) The finance subsystem SHALL maintain a count of implied-but-unlogged events (transaction present, corresponding log absent) and SHALL expose it as a quantified missingness estimate to the analysis layer, whether or not Joe answers any prompt.
**REQ-FIN-166** (Ubiquitous) The finance subsystem SHALL count bar and restaurant *visits and occasions* as the primary alcohol-context metric, and SHALL NOT present dollar amounts as the primary alcohol metric, because visit count is robust to price variance and to splitting while amount is not. ```

### D.2 Evidence tiers — what a link needs before it is shown
```
**REQ-FIN-170** (Ubiquitous) The finance subsystem SHALL assign every co-occurrence exactly one evidence tier from the closed set: T0 OBSERVED (a single dated fact, n=1, no pattern claimed); T1 DESCRIPTIVE (a count over a stated window, n >= 10, day-of-week reported alongside); T2 CO-OCCURRENT (a rate difference across a pre-registered condition, n >= 20 in the smaller arm, day-of-week controlled); T3 CAUSAL (reserved, and permanently unreachable by this subsystem on observational spend data).
**REQ-FIN-171** (Ubiquitous) The finance subsystem SHALL display a T0 co-occurrence only as a dated statement of what happened, and SHALL NOT attach any interpretation to it.
**REQ-FIN-172** (Ubiquitous) The finance subsystem SHALL NOT display a T1 co-occurrence where n is below 10.
**REQ-FIN-173** (Ubiquitous) The finance subsystem SHALL NOT display a T2 co-occurrence where the smaller arm contains fewer than 20 observations.
**REQ-FIN-174** (Ubiquitous) The finance subsystem SHALL NEVER assign tier T3 to any output.
**REQ-FIN-175** (Ubiquitous) The finance subsystem SHALL compute a co-occurrence only for a hypothesis Joe has previously registered in the `hypotheses` table, and the `cooccurrences` table SHALL carry a non-null foreign key to that hypothesis.
**REQ-FIN-176** (Unwanted behaviour) IF an analysis job would compute a correlation for which no registered hypothesis exists, THEN the finance subsystem SHALL abort the computation and SHALL log the attempted pairing, because correlating spend against sleep, mood, workouts, location, substances and productivity constitutes hundreds of implicit tests and something will always look significant.
**REQ-FIN-177** (Ubiquitous) Every T2 output SHALL include day-of-week as a controlled covariate, because Friday is both the high-work day and the social day and day-of-week alone will manufacture most apparent findings.
**REQ-FIN-178** (Ubiquitous) Every displayed co-occurrence SHALL state its n in the same sentence as its claim.
**REQ-FIN-179** (Ubiquitous) The finance subsystem SHALL exclude cash-derived and ATM transactions from every co-occurrence denominator and SHALL state the exclusion, because cash is a systematic and non-random blind spot concentrated on exactly the behaviour being examined.
**REQ-FIN-180** (Ubiquitous) The finance subsystem SHALL net inbound P2P transfers from any alcohol-context amount before that amount enters any co-occurrence, per REQ-FIN-050. ```

### D.3 Notice and ask — never conclude
```
**REQ-FIN-190** (Ubiquitous) Every co-occurrence surfaced to Joe SHALL be phrased as an observation followed by a question, and SHALL NOT be phrased as a conclusion.
**REQ-FIN-191** (Ubiquitous) The finance subsystem SHALL NEVER emit a statement asserting that one behaviour causes another.
**REQ-FIN-192** (Ubiquitous) The finance subsystem SHALL NEVER emit a personality-trait inference, a mood-state inference, or a mental-health inference from transaction data.
**REQ-FIN-193** (Unwanted behaviour) IF generated copy contains a causal connective ('because', 'causes', 'leads to', 'due to', 'makes you') linking a spend observation to a state observation, THEN the finance subsystem SHALL block publication of that copy and SHALL log a `copy_violation` row citing REQ-FIN-191.
**REQ-FIN-194** (Event-driven) WHEN a bar transaction is recorded with `occurred_at` after 21:00, the finance subsystem SHALL schedule exactly one annotation prompt for the following morning asking who Joe was with and how the morning is, and SHALL store the answer as an `annotations` row.
**REQ-FIN-195** (Ubiquitous) The annotation prompt SHALL be answerable in two taps and SHALL be dismissible without an answer.
**REQ-FIN-196** (Ubiquitous) The finance subsystem SHALL treat Joe's annotation as higher-ranked evidence than any inference, and SHALL supersede any inferred value with it.
**REQ-FIN-197** (Ubiquitous) The finance subsystem SHALL NEVER estimate alcohol volume, units or standard drinks from a transaction amount.
**REQ-FIN-198** (Optional feature) WHERE a bar tab amount is used as a prior on drink count, the finance subsystem SHALL store it with `lane='inferred'` and `confidence` no greater than 0.30, SHALL present it only as a question, and SHALL discard it the moment an actual `consume` atom exists for that episode.
**REQ-FIN-199** (Ubiquitous) The habit-rhythm engine SHALL use a circular histogram over day-of-week and hour-of-day with a chi-square test against uniform as its default method, and SHALL apply a Lomb-Scargle periodogram only where the series contains enough cycles for a false-alarm probability to be computed, refusing to report any peak that does not clear it.
**REQ-FIN-200** (Ubiquitous) The finance subsystem SHALL frame every habit output around fit with Joe's own stated goals rather than around restraint, and SHALL show the pattern beside those goals rather than naming the gap itself. ```

### D. NON-GOALS

- Diagnosing anything. Not stress, not depression, not a drinking problem, not a manic episode.
- Estimating blood alcohol, units, or drinks from spend. The eBAC machinery in `08_LENS_CONTEXT.md` §2.2 is fed by logged `consume` atoms and breathalyzer readings, never by transactions.
- Automated hypothesis generation. The `hypotheses` table is written by Joe, not by the system.
- A "correlation explorer" that lets Joe browse arbitrary pairings. That is p-hacking with a UI.
- Real-time intervention. No notification while Joe is at the bar. The system speaks the next morning at the earliest.
- Any claim about *why* Joe did something. The data cannot distinguish a night out with close friends from a night drinking alone, and those produce identical transactions.

### D. ALTERNATIVES CONSIDERED

- **Reporting mood-spend correlations without pre-registration.** Rejected: the only published N=1 attempt found null results across frequency, volume and burstiness, so any "finding" this system produces on a smaller sample is far more likely to be a multiple-comparisons artefact than a signal.
- **Using the gambling-detection playbook for alcohol.** The Monzo/BIT study worked because gambling has a dedicated MCC (7995) and unambiguous merchant identities; ~11% of customers had gambling transactions, averaging £136/month, with above-average gamblers showing ~1 transaction/day, Thursday-to-Saturday concentration, and a savings ratio of 0.1× versus 42×. Alcohol sits *between* gambling and mood: merchant-identifiable but polluted by restaurants-with-bars, groceries and splitting. The structural metrics that worked there — concentration, frequency, day-of-week clustering — are adopted; the confidence is not.
- **Spend burstiness as a psychological feature** (from the 54-feature Tovanich design). Available and cheap to compute, but the N=1 study specifically tested burstiness against mood and found no significant difference. Computed and stored, never surfaced.
- **Trait inference framed as "for your eyes only."** Rejected. The privacy framing does not repair the measurement error; AUROC 0.558 is near chance whether or not anyone else sees it.
- **Telling Joe his own hypothesis is confirmed.** Deliberately structurally impossible above T2. The self-fulfilling-narrative hazard is real: telling him "you drink when stressed" installs a script he may then act out.

### D. UNRESOLVED QUESTIONS

- **What are Joe's actual pre-registered hypotheses?** The `hypotheses` table is a foreign-key constraint with nothing in it until he writes them. This is a blocking dependency for anything in §D.2.
- **The n thresholds (10 for T1, 20 per arm for T2) are this document's choices, not the research's.** The research says "refuse to display anything below a pre-set n and effect threshold" without naming numbers, and notes that at ~10–40 discretionary transactions per week a six-week pattern is six data points. The specific integers need Joe's sign-off.
- **What is the correct effect-size floor?** Unspecified. n alone is not sufficient protection.
- **How does mood get onto a `subject_day` at all?** Depends on `07_LENS_MIND.md` check-in compliance, which is itself missing-not-at-random and likely to fail on exactly the high-stress days the hypothesis concerns.
- **Is ±3 hours the right window for transaction-to-consume matching?** Inherited from `08_LENS_CONTEXT.md` §7.3's sketch; not derived.
- **How is "a lot of work" operationalised?** Joe's phrasing is qualitative. Calendar density, logged hours, or self-report are all candidates and they will not agree.
- **What happens when a hypothesis is disconfirmed?** Nothing in this document says how, or whether, to tell him.

## §E — PRESENTATION RESTRAINT

The governing evidence is Pocheptsova Ghosh & Huang. Precise, frequent budget feedback caused **overspending of ~$40 (n=283, p=.002)** and **$32.00 (n=363)**. A **range** instead of an exact figure attenuated the effect (n=198). **Splitting the budget into sub-categories increased total spending** (n=251). The mechanism: certainty removes the safety margin — when you do not know exactly how much is left you keep a buffer; a precise app tells you exactly how much room you have and you spend into it.

The convenient consequence: a $0 architecture built on monthly CSV imports naturally produces retrospective, low-frequency review. **The cheap architecture is the behaviourally correct one.**

The positive prescription comes from motivational interviewing: express empathy, develop discrepancy, roll with resistance, support self-efficacy, and explicitly resist the "righting reflex." The evidence that shame backfires is strong from adjacent domains — weight discrimination is associated with ~60% increased mortality risk independent of BMI, and experiencing weight stigma in the lab *increases* eating and decreases self-regulation.
```
**REQ-FIN-210** (Ubiquitous) The finance subsystem SHALL NOT display a running count of money spent or money remaining in the current period.
**REQ-FIN-211** (Ubiquitous) The finance subsystem SHALL NOT display any figure that updates more than once per 24 hours.
**REQ-FIN-212** (Ubiquitous) The finance subsystem SHALL express every forward-looking amount as a range whose width is at least 20% of its midpoint, and SHALL NOT express any forward-looking amount as a single number.
**REQ-FIN-213** (Ubiquitous) The finance subsystem SHALL present at most one scheduled review per 7-day period.
**REQ-FIN-214** (Ubiquitous) The finance subsystem SHALL NOT define, store or display a budget target for any individual category.
**REQ-FIN-215** (Ubiquitous) The finance subsystem SHALL NOT render a pie chart, a donut chart, or any other part-to-whole visual of spending by category.
**REQ-FIN-216** (Ubiquitous) The finance subsystem SHALL present concentration of spend as a ranked list of merchants and categories with absolute amounts and counts, and SHALL NOT present it as a share of a total.
**REQ-FIN-217** (Ubiquitous) The finance subsystem SHALL present every retrospective amount as an observed figure for a closed period, paired with the same figure for the preceding period.
**REQ-FIN-218** (Ubiquitous) The finance subsystem SHALL NEVER emit any of the following words in reference to Joe's spending: 'excessive', 'wasteful', 'unnecessary', 'too much', 'splurge', 'guilty', 'overspent', 'bad', 'should have'.
**REQ-FIN-219** (Unwanted behaviour) IF generated copy contains any word on the REQ-FIN-218 list, THEN the finance subsystem SHALL block publication of that copy and SHALL write a `copy_violation` row citing REQ-FIN-218 and the offending token.
**REQ-FIN-220** (Ubiquitous) The finance subsystem SHALL express every observation in numbers, counts and timestamps, and SHALL NOT express any observation in quantity adjectives.
**REQ-FIN-221** (Ubiquitous) Every insight surfaced SHALL carry a 'not useful' control, and activating it SHALL suppress that entire insight class permanently.
**REQ-FIN-222** (Ubiquitous) The finance subsystem SHALL show a pattern beside Joe's own stated goals and SHALL let him name any gap, and SHALL NOT name the gap itself.
**REQ-FIN-223** (Ubiquitous) The periodic review SHALL include a running record of changes Joe has already made and their recorded effect, per REQ-FIN-156.
**REQ-FIN-224** (Ubiquitous) The finance subsystem SHALL label every figure affected by cash, splitting or missing coverage with the specific limitation in the same view — 'destination unknown' for ATM withdrawals, 'net of $N reimbursed' for split tabs, and the n for every inference.
**REQ-FIN-225** (State-driven) WHILE any account has had no successful import for more than 35 days, the finance subsystem SHALL display a coverage warning naming that account on every aggregate view and SHALL NOT present any total as complete.
**REQ-FIN-226** (Ubiquitous) The finance subsystem SHALL send at most 4 notifications per calendar month, excluding the twice-yearly renewal review.
**REQ-FIN-227** (Ubiquitous) The finance subsystem SHALL make every alcohol-context surface speak in occasions and context rather than in volume and cost.
**REQ-FIN-228** (Ubiquitous) Copy describing a coping behaviour SHALL NOT characterise it as a malfunction, because the published finding is that making purchase decisions restores a sense of personal control and measurably reduces residual sadness. ```

### E. NON-GOALS

- A daily dashboard. The surface Joe opens should be worth opening, which means it should not be there most days.
- Envelope or zero-based budgeting (the YNAB method). It is a genuine method and it works for people who want it; it is also the maximally precise, maximally frequent version of the exact intervention that backfired.
- Gamification: streaks, scores, badges, "you beat last month."
- Push notification on transaction. The alert email already exists; the system's job is to store it silently.
- Comparison against anyone else — national averages, peer benchmarks, "people like you."
- A projected end-of-month total. Forward-looking point estimates are forbidden by REQ-FIN-212 and a projection is the most tempting one.

### E. ALTERNATIVES CONSIDERED

- **A precise remaining-budget counter.** Rejected. It is the single identified intervention with measured evidence of harm ($32–40 overspend across two field studies, n=283 and n=363).
- **A range-based remaining-budget counter** ("roughly $150–250 left, at your usual pace"). This is the research's own suggested phrasing and Lab Study 4 shows the range attenuates the effect. Still rejected as a *live counter* under REQ-FIN-211, but permitted inside a low-frequency retrospective review. This is the one place where this document is stricter than the research strictly requires, and it is deliberate: attenuated is not eliminated.
- **Many small category budgets.** Rejected on direct evidence: Field Study 5 (n=251) found sub-category budgets *increased* total spending via mental-accounting justification.
- **Shorter budget windows and roll-over reminders.** These are listed in the research among interventions that *did* help. Not adopted in v1 because both imply a budget, and no budget exists in this design. Recorded as a genuine open option if Joe later wants one.
- **The Copilot Money model** — a beautiful retrospective review surface plus a corrections-learning categorizer. This is philosophically the closest commercial relative and the categorizer design in §B is essentially it. The daily-open aesthetic is not adopted.
- **Actual Budget as the direct model.** Closest philosophical relative overall — open source, local-first, explicit rules engine, self-hostable — but it is envelope-method at its core.

### E. UNRESOLVED QUESTIONS

- **What cadence does Joe actually want?** REQ-FIN-213 sets one review per 7 days. The research recommends "weekly digest plus event-triggered moments" but the weekly figure is a recommendation, not a measurement.
- **Is 20% the right minimum range width (REQ-FIN-212)?** Lab Study 4 establishes that ranges attenuate the effect; it does not report the range width used.
- **Is 4 notifications/month right (REQ-FIN-226)?** Invented. Needs Joe's tolerance, measured.
- **What is the ban-list enforcement mechanism?** REQ-FIN-219 requires blocking, but token-matching will produce false positives ("the gym charge was unnecessary to keep" in Joe's own annotation text). Whether the ban applies to system-generated copy only, or also to Joe's own words echoed back, is unresolved — this document assumes system-generated only.
- **Does "no pie chart" (REQ-FIN-215) survive contact with Joe?** He asked to "see where I spend the most", and a ranked list answers that. But the pie-chart prohibition is the one surviving clause of the old doctrine that he did not explicitly address, and it is being carried forward on this document's judgment rather than on his instruction.
- **How does the coverage warning (REQ-FIN-225) avoid becoming the nagging the system is designed not to do?**

## §F — NEVER-RULES FOR THIS SUBSYSTEM

These are absolute. They are restated here as their own requirements so that a violation is a spec violation with an ID, not a matter of taste. Every one is testable.
```
**REQ-FIN-240** (Ubiquitous) The finance subsystem SHALL NEVER require a recurring payment to function.
**REQ-FIN-241** (Ubiquitous) The finance subsystem SHALL NEVER store a bank username, password, PIN or security answer.
**REQ-FIN-242** (Ubiquitous) The finance subsystem SHALL NEVER transmit a raw transaction descriptor together with any location coordinate to a third-party service.
**REQ-FIN-243** (Ubiquitous) The finance subsystem SHALL NEVER include location coordinates, mood values, health measurements or substance logs in any prompt sent to an external model.
**REQ-FIN-244** (Ubiquitous) The finance subsystem SHALL NEVER delete a `raw_documents` or `raw_transactions` row.
**REQ-FIN-245** (Ubiquitous) The finance subsystem SHALL NEVER overwrite a value that Joe set directly.
**REQ-FIN-246** (Ubiquitous) The finance subsystem SHALL NEVER assert that a purchase was necessary or unnecessary.
**REQ-FIN-247** (Ubiquitous) The finance subsystem SHALL NEVER assert a causal relationship between a state and a purchase.
**REQ-FIN-248** (Ubiquitous) The finance subsystem SHALL NEVER emit a personality-trait or mental-health inference.
**REQ-FIN-249** (Ubiquitous) The finance subsystem SHALL NEVER convert a transaction amount into a quantity of alcohol.
**REQ-FIN-250** (Ubiquitous) The finance subsystem SHALL NEVER display a live or continuously updating spending figure.
**REQ-FIN-251** (Ubiquitous) The finance subsystem SHALL NEVER initiate a payment, a transfer, a cancellation or any other state change at a financial institution.
**REQ-FIN-252** (Ubiquitous) The finance subsystem SHALL NEVER re-guess a category that Joe has corrected.
**REQ-FIN-253** (Ubiquitous) The finance subsystem SHALL NEVER re-raise an insight class that Joe has marked 'not useful'.
**REQ-FIN-254** (Ubiquitous) The finance subsystem SHALL NEVER surface a correlation for which no pre-registered hypothesis exists.
**REQ-FIN-255** (Ubiquitous) The finance subsystem SHALL NEVER drive a browser session against a financial institution.
**REQ-FIN-256** (Ubiquitous) The finance subsystem SHALL NEVER present a total as complete while any account's coverage gap exceeds 35 days.
**REQ-FIN-257** (Ubiquitous) The finance subsystem SHALL NEVER discard the time-of-day carried by an alert email.
**REQ-FIN-258** (Ubiquitous) The finance subsystem SHALL NEVER compare Joe's spending to a population average, a peer group, or any external benchmark. ```

### F. NON-GOALS

- Making the never-rules configurable. A settings toggle that disables REQ-FIN-246 or REQ-FIN-248 is a way of shipping the prohibited behaviour with a consent screen in front of it.
- Encoding the never-rules only in prompts or in documentation. Where a rule can be a database constraint or a blocking test, it must be one.
- Soft enforcement. A rule that logs a warning and proceeds is not a never-rule.

### F. ALTERNATIVES CONSIDERED

- **An "advanced mode" unlocking trait inference and precise counters.** Rejected. The measurement error does not change when the user opts in; the numbers are still near-chance, and a system that shows near-chance output on request is a system that shows near-chance output.
- **Enforcing the copy rules with an LLM reviewer rather than a token ban-list.** More flexible, catches paraphrase, and would catch the causal-connective cases a regex misses. Rejected as the *sole* mechanism because it is not deterministic and cannot be unit-tested; recorded as a viable second layer on top of the deterministic ban-list.
- **Allowing SimpleFIN behind a feature flag.** Rejected. A flag is a code path, and REQ-FIN-004 forbids a code path that requires payment. The adapter interface (REQ-FIN-030) already provides everything a future reversal would need, at zero cost today.
- **A weaker cash rule** — imputing likely destinations for ATM withdrawals from surrounding context. Rejected: the imputation would be most confident exactly where it is most wrong, on nights out.

### F. UNRESOLVED QUESTIONS

- **Which never-rules can actually be expressed as database constraints?** REQ-FIN-245 and REQ-FIN-252 look like triggers; REQ-FIN-254 is a foreign key; REQ-FIN-248 is only expressible as a test over generated copy. The enforcement mechanism for each is unassigned.
- **Who can amend this list?** Only Joe, in writing, is the assumption — but the amendment procedure is not specified, and this document exists precisely because a prior prohibition was overturned verbally.
- **How is REQ-FIN-243 enforced across the whole prompt-construction layer**, which lives in `09_PROGRAM.md` and not here?
- **Does REQ-FIN-244's never-delete rule conflict with any data-retention or right-to-erasure obligation?** Single-user self-hosted, so probably not, but unexamined.

## §G — GHERKIN ACCEPTANCE SCENARIOS

Each scenario is executable and cites the requirement IDs it covers. Data is concrete on purpose.

---

**Scenario 1 — Triple-source dedupe with a voice note on the same subject_day**
_Covers: REQ-FIN-021, REQ-FIN-022, REQ-FIN-040, REQ-FIN-043, REQ-FIN-044, REQ-FIN-045, REQ-FIN-160, REQ-FIN-162_
```gherkin
Given a Chase alert email received 2026-03-14 12:41:07 with body
      "Card ending 4417: $11.63 at MCDONALDS F1234 SEATTLE WA"
And   a Gmail receipt from mcdonalds@email.mcdonalds.com timestamped
      2026-03-14 12:41 with line items "Big Mac Meal $9.79, Apple Pie $1.84"
And   a Chase CSV imported 2026-03-18 containing the row
      "03/16/2026,MCDONALD'S F1234,-11.63"
And   a voice-note atom on subject_day 2026-03-14 with text
      "had a big mac for lunch"
When  all four artifacts have been ingested
Then  exactly one canonical transaction SHALL exist for $11.63
And   its sources[] SHALL contain ['email_alert','email_receipt','csv']
And   its occurred_at SHALL be 2026-03-14T12:41:07
And   its posted_at SHALL be 2026-03-16
And   two transaction_items rows SHALL exist
And   the voice-note atom SHALL NOT be merged into the transaction
And   a cooccurrence row SHALL link the transaction and the voice note on
      subject_day 2026-03-14 at tier T0
```

---

**Scenario 2 — The same CSV imported twice**
_Covers: REQ-FIN-011, REQ-FIN-012, REQ-FIN-043, REQ-FIN-044, REQ-FIN-047_
```gherkin
Given the file "chase_2026_02.csv" containing 84 rows has been imported
      successfully and produced 84 canonical transactions
When  the byte-identical file is emailed to the ingest address a second
      time on a later date
Then  raw_documents SHALL contain exactly one row for that SHA-256 hash
And   that row's duplicate_delivery_count SHALL equal 1
And   zero new raw_transactions rows SHALL be created
And   the canonical transaction count SHALL remain 84
When  a third CSV covering 2026-01-23 to 2026-02-22 is imported
Then  raw_documents SHALL contain a second row with a different hash
And   transactions falling in the 9-day overlap SHALL NOT be duplicated
And   each overlapping transaction's sources[] SHALL list both documents
And   any observation matching two canonical candidates SHALL produce a
      review_queue row with status 'ambiguous_dedupe' rather than a merge
```

---

**Scenario 3 — A category Joe corrects, which must never be re-guessed**
_Covers: REQ-FIN-100, REQ-FIN-101, REQ-FIN-102, REQ-FIN-103, REQ-FIN-252_
```gherkin
Given the descriptor "SQ *THE ANGRY BEAVER 8005551212 WA" was
      auto-categorized as "Restaurants" by the knn layer at confidence 0.71
When  Joe corrects the category to "Bars"
Then  the transaction's category_source SHALL be 'user'
And   its confidence SHALL be 1.0
And   corrected_at SHALL be non-null
And   the descriptor hash, the merchant default and category_embeddings
      SHALL all be updated in the same database transaction
And   all 14 prior uncorrected transactions sharing that descriptor hash
      SHALL be recategorized to "Bars" with category_source
      'user_propagated'
When  the nightly recategorization job subsequently runs
Then  the category of every one of those transactions SHALL remain "Bars"
And   no layer SHALL emit a competing suggestion for that descriptor
```

---

**Scenario 4 — A bar tab on a high-stress workday**
_Covers: REQ-FIN-161, REQ-FIN-162, REQ-FIN-166, REQ-FIN-171, REQ-FIN-190, REQ-FIN-194, REQ-FIN-197_
```gherkin
Given a transaction of $64.00 at "The Angry Beaver" with
      occurred_at 2026-03-19T23:47:00 and posted_at 2026-03-20
And   a calendar atom on subject_day 2026-03-19 showing 9.5 logged work
      hours
And   a mood atom on subject_day 2026-03-19
When  the linkage engine runs
Then  a cooccurrence row SHALL be created on subject_day 2026-03-19,
      not 2026-03-20
And   its evidence tier SHALL be T0
And   an annotation prompt SHALL be scheduled for the morning of
      2026-03-20 asking who Joe was with and how the morning is
And   no output SHALL contain an estimated drink count, unit count, or
      eBAC value derived from the $64.00
And   any surfaced text SHALL end in a question
```

---

**Scenario 5 — The same pattern at n=9, below the display threshold**
_Covers: REQ-FIN-172, REQ-FIN-173, REQ-FIN-175, REQ-FIN-177, REQ-FIN-178_
```gherkin
Given Joe has pre-registered the hypothesis
      "bar visits follow days with more than 9 logged work hours"
And   9 bar visits exist in the last 90 days, 7 of them following a 9h+ day
When  the analysis job runs
Then  no T1 or T2 output SHALL be displayed, because n=9 is below 10
And   the finding SHALL be retained internally with its n
When  n subsequently reaches 12
Then  a T1 output MAY be displayed
And   it SHALL state "7 of 12" and SHALL report the day-of-week
      distribution alongside
And   it SHALL NOT contain the words 'because', 'causes' or 'leads to'
```

---

**Scenario 6 — An unregistered correlation is attempted**
_Covers: REQ-FIN-175, REQ-FIN-176, REQ-FIN-254_
```gherkin
Given the hypotheses table contains no row pairing "coffee spend" with
      "sleep duration"
When  an analysis job attempts to compute that correlation
Then  the job SHALL abort the computation
And   SHALL write a log row naming the attempted pairing and REQ-FIN-176
And   no cooccurrence row SHALL be created
And   nothing SHALL be surfaced to Joe
```

---

**Scenario 7 — A subscription Joe forgot**
_Covers: REQ-FIN-130, REQ-FIN-137, REQ-FIN-150, REQ-FIN-151, REQ-FIN-157, REQ-FIN-113, REQ-FIN-246_
```gherkin
Given a recurring stream for "Seattle Bouldering Project" at $45.00 with
      a median interval of 30 days, status 'active', matured at n=7
And   zero place_visit atoms inside that venue's geofence in the last 71
      days
And   the stream's next expected charge date is 2026-04-02
When  the nightly usage-join job runs on 2026-03-20
Then  an insight SHALL be created but SHALL NOT be delivered
And   it SHALL be scheduled for delivery on 2026-04-02
When  2026-04-02 arrives
Then  the insight SHALL be delivered
And   it SHALL state "$45/mo, last visit 71 days ago"
And   it SHALL NOT contain the words 'necessary', 'unnecessary' or
      'wasteful'
And   it SHALL end in a question
And   it SHALL carry a 'not useful' control
```

---

**Scenario 8 — A price rise on a stream**
_Covers: REQ-FIN-134, REQ-FIN-135, REQ-FIN-220_
```gherkin
Given a recurring stream for "Spotify" with amounts
      [10.99 × 8 months, 11.99 × 2 months]
When  the recurrence engine runs
Then  the stream's amount behaviour SHALL be classified 'fixed_with_step'
And   an insights row SHALL state the previous amount 10.99, the new
      amount 11.99 and the month of the change
And   the text SHALL contain no quantity adjective
```

---

**Scenario 9 — A split bar tab netted against Venmo**
_Covers: REQ-FIN-049, REQ-FIN-050, REQ-FIN-166, REQ-FIN-180, REQ-FIN-224_
```gherkin
Given an outbound transaction of $180.00 at a bar with occurred_at
      2026-05-08T22:15:00
And   three inbound Venmo receipts of $45.00 each on 2026-05-09
When  the transfers linkage job runs
Then  a transfers row SHALL link each inbound receipt to the $180.00
      transaction
And   any alcohol-context metric SHALL use $45.00, not $180.00
And   the display SHALL show "$45 net of $135 reimbursed"
And   the primary metric shown SHALL be the visit count, not the amount
```

---

**Scenario 10 — A $120 ATM withdrawal**
_Covers: REQ-FIN-051, REQ-FIN-179, REQ-FIN-224_
```gherkin
Given an ATM withdrawal of $120.00 on 2026-05-08T21:40:00
When  the monthly review is rendered
Then  the withdrawal SHALL appear labelled 'destination unknown'
And   its $120.00 SHALL NOT be included in any category rollup
And   it SHALL be excluded from every co-occurrence denominator
And   the exclusion SHALL be stated on the view
```

---

**Scenario 11 — Presentation restraint under load**
_Covers: REQ-FIN-210, REQ-FIN-211, REQ-FIN-212, REQ-FIN-214, REQ-FIN-215, REQ-FIN-216, REQ-FIN-225_
```gherkin
Given the current month is 2026-06 and 12 days have elapsed
And   the Amex account's last successful import was 41 days ago
When  Joe opens the finance surface
Then  no figure labelled "remaining" or "left this month" SHALL be
      rendered
And   no rendered figure SHALL have updated within the last 24 hours
And   no pie or donut chart SHALL be rendered
And   spend concentration SHALL be rendered as a ranked list of merchants
      with absolute amounts and counts, not as percentage shares
And   any forward-looking amount SHALL be rendered as a range whose width
      is at least 20% of its midpoint
And   a coverage warning naming the Amex account SHALL be displayed
And   no total SHALL be presented as complete
```

---

**Scenario 12 — Banned copy is blocked at publication**
_Covers: REQ-FIN-193, REQ-FIN-218, REQ-FIN-219_
```gherkin
Given a generated insight with the text
      "You overspent on bars — 9 visits is excessive, probably because of
       your work stress"
When  the copy gate evaluates it
Then  publication SHALL be blocked
And   a copy_violation row SHALL be written citing REQ-FIN-218 with tokens
      ['overspent','excessive']
And   a second copy_violation row SHALL be written citing REQ-FIN-191 for
      the connective 'because of'
And   nothing SHALL be shown to Joe
```

---

## §H — TRACEABILITY

| Section | ID range | Count |
|---|---|---|
| §0 Doctrine | REQ-FIN-001 … 004 | 4 |
| §A Ingestion | REQ-FIN-010 … 051 | 34 |
| §B Merchant & category | REQ-FIN-060 … 106 | 29 |
| §C Necessity | REQ-FIN-110 … 158 | 31 |
| §D Habit linkage | REQ-FIN-160 … 200 | 29 |
| §E Presentation | REQ-FIN-210 … 228 | 19 |
| §F Never-rules | REQ-FIN-240 … 258 | 19 |
| **Total** | | **165** |

EARS pattern distribution: Ubiquitous 112, Event-driven 31, Unwanted behaviour 16, Optional feature 4, State-driven 2. Gherkin scenarios: 12. Occurrences of SHOULD: 0.

**Build order** (inherited from the research, and unchanged by this document): schema + CSV/QFX importer + merchant normalization + review queue → categorization cascade with pgvector kNN → email alert ingest and dedupe → recurring stream detection → usage-evidence join and the twice-yearly ritual → receipt line items → behavioural linkage with pre-registered hypotheses → Teller adapter, only if the manual step becomes genuinely annoying.
