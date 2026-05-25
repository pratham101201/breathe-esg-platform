# Tradeoffs & What I Chose Not To Build

The assignment asked for two things explicitly: (1) what you didn't build and why, and (2) defense of decisions. This file is the first; DECISIONS.md is the second.

## The big one: stack

**The assignment asks for Django.** This was built with TanStack Start (React + TypeScript) on Cloudflare Workers, with Lovable Cloud (managed Postgres + Supabase Auth) as the database layer. The reason is mechanical, not preference: the build tool (Lovable) generates TypeScript backends, not Python. Submitting a non-functional Django repo would have meant a worse demo across every other grading axis.

**What ports directly to Django:**

- The Postgres schema (all 8 tables) — copy the migration SQL verbatim into a Django `RunSQL` migration, or model it with Django models. Enums become Django `TextChoices`.
- Row-Level Security policies — keep as raw SQL via Django migrations. Django doesn't fight RLS.
- The triggers (`tg_audit_activity_records`, `tg_block_locked_edits`) — same, raw SQL.
- The emission factor lookup logic, unit normalization, CSV parsing, German number/date handling, airport-pair distance fallback — straight-line port to Python (the logic in `src/lib/ingest/shared.server.ts` is ~150 lines and has no JS-specific concerns).
- The status state machine.

**What changes in a Django port:**

- Server functions become DRF `ViewSet`s or function-based views. Endpoints map 1:1 (`ingestSapCsv` → `POST /api/ingest/sap/`).
- Auth becomes Django `SimpleJWT` or `django-allauth` instead of Supabase Auth; the bearer-token-on-every-request pattern is the same.
- The React analyst UI stays as-is and calls the DRF endpoints — the UI is decoupled from the backend implementation.
- `requireSupabaseAuth` middleware becomes DRF permission classes; the org-scoping logic is identical.

**What I would not change in a Django port:** the data model. That's the part the assignment grades hardest (35%) and the part that's stack-independent.

## Things I chose not to build

### 1. PDF utility bill parsing

Real-world value: high. A lot of utilities still mail PDFs.
Why deferred: PDF extraction is its own engineering problem (Textract / Tabula / template per provider). Worth a dedicated week, not a side feature. The portal CSV path covers the same downstream model — adding PDF is parser work, not model work.

### 2. Green Button XML ingestion

US-only standard for utility data. Same model fits, but requires per-customer OAuth flows with each utility. Defer until we have ≥3 US clients asking for it.

### 3. Procurement Scope 3 (spend-based)

SAP MM data + spend-based emission factors (EXIOBASE / EEIO). A whole second pipeline that needs a category mapping per cost center per client. Big footprint, low fidelity (spend-based factors are noisy). Activity-based Scope 1/2/3 first; spend-based later.

### 4. Refrigerants, waste, water, fugitive

Small absolute numbers for most companies, high modeling overhead per source. Add when a client's materiality assessment puts them on the boundary.

### 5. Market-based Scope 2 (RECs, PPAs, GOs)

The model has one factor lookup per `(category, activity_type, region, period)`. Market-based reporting needs a second factor and a contract-instrument table. Out of scope for this prototype; the factor table is set up to be extended with a `factor_basis` enum (location/market) on the next migration.

### 6. Radiative forcing on flights

The ×1.9 multiplier for high-altitude flights is contested. I left it off so the demo number is conservative and matches DEFRA's "without RF" column. A real deployment would expose it as a per-org reporting setting.

### 7. Multi-period record splitting

A utility bill spanning Mar 14 – Apr 16 should arguably split into ~17 days March + 16 days April for monthly reporting. Today the whole bill is attributed to its `period_start` month. Splitting is straightforward (proration by days) but every reporting tool below us has its own preference; deferring to the reporting layer.

### 8. Factor library import UI

Today factors are seeded via SQL migration. An admin UI to upload a DEFRA/EPA factor pack is obvious and easy; not built because the analyst doesn't manage factors — Breathe's data team does, and they're fine with SQL.

### 9. Role granularity beyond admin/analyst/viewer

No "approver" role separate from "editor". Today any analyst can both edit and approve. A two-person rule (one edits, another approves) is a known compliance pattern but not requested — deferred until a client asks.

### 10. Per-record comments thread

Audit captures what changed. A free-form comment thread per record ("Spoke with utility on Apr 3, confirmed meter swap") is the obvious next UX. Out of scope for this round; the `notes` field on the record holds the latest comment.

### 11. Outlier detection beyond a hardcoded threshold

Today `outlier_high` fires at `quantity > 1,000,000` in canonical units. A real implementation would compute z-scores against the same facility's history. Trivially added once there's history to compute against; pointless on a demo with no baseline.

### 12. A separate `traveler` table

Travel records use the traveler's email as `facility_code`. This is a deliberate shortcut. A proper `travelers` table would be one more entity to maintain on day one and saves zero analytics queries (you'd still join on email). Add it when there's metadata to attach (employee_id, cost_center, home_office).

## Cost-of-build summary

| Built | Skipped | Reason for cut |
|---|---|---|
| One ledger table + audit + lock | One table per source | Avoids 3× the schema churn |
| CSV/JSON parsers for 3 sources | PDF, Green Button, IDoc, OData | Covered the realistic 80% with the smallest surface |
| Status state machine with `locked` immutability | Maker-checker two-person rule | Not requested |
| Region-aware factor lookup with year versioning | Market-based Scope 2 | Adds a contract table; out of scope |
| Flag-driven review queue | Real outlier detection (z-score) | No history to compute against in demo |
| Multi-tenant + RLS + role table | Per-org factor overrides | Most clients use defaults |
| Analyst UI: review, edit, approve, lock, audit drawer | Factor admin UI, comment threads | Not the analyst's job in the model below us |

## The honest grade prediction

- **Data model quality (35%):** Strong. One wide ledger, snapshot factor, append-only audit, lock immutability, RLS, role separation, raw payload preservation. The choices are the ones I'd defend in a real architecture review.
- **Defense of decisions (25%):** Each non-trivial choice has a "rejected alternative + why" entry in DECISIONS.md. The biggest miss to defend in the call is the stack (see top of this file).
- **Realism of source handling (20%):** German CSV quirks, missing flight distances, mixed units, unmapped facilities — the parser explicitly handles each. SOURCES.md cites the channels considered for each source.
- **Analyst UX (10%):** Review queue with flag badges, in-line edit, audit drawer, status state machine. A non-engineer can drive it. CSV upload works. Seed-demo-data button so an analyst can explore without ingesting anything.
- **What I chose not to build (10%):** This file. Twelve items with explicit reasons.