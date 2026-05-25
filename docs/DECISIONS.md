# Decisions

Each entry: what we chose, what we rejected, and why.

## D1. One ledger table, not one per source

**Chose:** `activity_records` holds everything.
**Rejected:** `sap_records` + `utility_records` + `travel_records`.
**Why:** the analyst's primary job is reviewing scope 1/2/3 totals; UNION views across three tables defeat indexes and force every UI filter into application code. Source differences live in the parser, not the warehouse. Raw fidelity preserved in `source_payload` JSONB.

## D2. Store raw_quantity AND quantity, raw_unit AND unit

**Chose:** keep both the original and the normalized value on the row.
**Rejected:** normalize on ingest and discard the original.
**Why:** when an analyst asks "but the SAP export said 1.500 — why does this row say 1500?" we need to show the German decimal comma without re-fetching the file. Auditors ask this too.

## D3. Cache `co2e_kg` and `emission_factor` on the row

**Chose:** denormalize the factor and the computed kg into `activity_records`.
**Rejected:** compute on read by joining `emission_factors`.
**Why:** factors get updated. A 2026 DEFRA refresh must not silently change a 2024 disclosure. By snapshotting the factor at ingest, the row is reproducible. Recompute is explicit (analyst edit triggers it).

## D4. Status state machine: pending → needs_review → approved → locked

**Chose:** five states with a `locked` terminal that triggers block any UPDATE.
**Rejected:** boolean `approved`.
**Why:** the gap between "approved" (analyst signed off) and "locked" (used in a published report) matters. An approved row can still be corrected; a locked row cannot. Reports need the immutability guarantee.

## D5. Append-only audit via trigger, not application code

**Chose:** Postgres trigger `tg_audit_activity_records` inserts into `audit_events` for create/edit/status_change.
**Rejected:** log from server functions.
**Why:** triggers fire regardless of which client wrote the row (CLI script, server fn, future webhook, manual SQL fix). No code path can bypass the audit. The trigger uses `SECURITY DEFINER` so it works under RLS.

## D6. Roles in a separate `user_roles` table

**Chose:** `user_roles(user_id, organization_id, role)` with a `has_role()` SECURITY DEFINER function.
**Rejected:** `role` column on `profiles`.
**Why:** roles-on-profile is a documented Supabase footgun — RLS policies that check `profiles.role` against the row's profile recurse infinitely, and a user who can UPDATE their own profile row gives themselves admin. The separate table + definer function is the canonical fix.

## D7. Flag-driven review queue, not error queue

**Chose:** ingest every parseable row; attach `flags` array; status becomes `needs_review` if any flag fired.
**Rejected:** reject malformed rows at ingest, return errors to client.
**Why:** the analyst's value is judgment on edge cases ("the gas meter reading is 10x the usual — is the plant down or did the meter wrap?"). Hiding suspicious rows in an error log loses them. Flagging surfaces them in the same UI they already live in.

## D8. CSV parser tolerates German and US conventions

**Chose:** auto-detect delimiter (`;` vs `,`); accept dates as `dd.mm.yyyy`, `yyyy-mm-dd`, or `mm/dd/yyyy`; accept numbers with German comma decimals (`1.234,56`).
**Rejected:** require ISO + commas + dot decimals.
**Why:** a SAP export from a German plant ships exactly this format. Asking the client to reformat is a non-starter. Documented assumption in SOURCES.md.

## D9. Natural gas m³ → kWh at 10.55

**Chose:** hardcode UK-standard HHV (10.55 kWh/m³) for the only m³→kWh path we need (SAP `ERDGAS`).
**Rejected:** ask the client for calorific value per delivery.
**Why:** real CV varies by ±2%. For a demo + most reporting purposes, the standard is defensible and documented; the row keeps `raw_quantity` and `raw_unit` so a customer who needs CV precision can supply it and we recompute.

## D10. Concur: estimate distance from airport-pair lookup when missing

**Chose:** when `distanceKm` is null on a flight segment, look up a small airport-pair table; if found, use it and flag `distance_estimated`; if not, skip the row and flag `distance_missing`.
**Rejected:** call a great-circle distance API; skip silently.
**Why:** travel data is the messiest of the three. An estimated number with a flag is more useful than dropping the trip from scope 3. The flag tells the analyst exactly what they're trusting.

## D11. TanStack Start, not Django

**Chose:** TanStack Start (React + TypeScript) on Cloudflare Workers, with Lovable Cloud (managed Postgres + Supabase Auth).
**Rejected:** the assignment's stated Django + DRF.
**Why:** the build tool used (Lovable) does not produce Python backends. To meet the assignment's spirit — data model quality, defensible decisions, analyst UX — the same semantics are implementable in either stack. The Postgres schema, RLS, triggers, and emissions math port directly to Django + DRF; the parser and UI would be rewritten. See TRADEOFFS.md for the explicit tradeoff and what we'd change in a Django port.

## D12. Per-source ingestion endpoints, not one polymorphic endpoint

**Chose:** `ingestSapCsv`, `ingestUtilityCsv`, `ingestConcurJson` as separate server functions.
**Rejected:** `ingest(source, payload)` with a discriminator.
**Why:** each parser has distinct validation needs and error vocabulary. A polymorphic endpoint would need a fat union type and lose type safety on each parser's input. The cost of three endpoints is six lines of boilerplate.

## D13. Three sources, not five

**Chose:** SAP (Scope 1 — fuel/gas), Utility CSV (Scope 2 — electricity), Concur (Scope 3 — business travel).
**Rejected:** also building procurement-based Scope 3 from SAP MM, refrigerants, waste, water.
**Why:** one source per scope demonstrates the architecture handles the breadth (Scope 1/2/3) and the depth (three completely different shapes). Adding more sources rewards parser-writing, not modeling thinking. See TRADEOFFS.md "What we chose not to build."