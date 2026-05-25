# Data Model

## Goal

Take messy data from three very different client sources (SAP fuel/procurement, utility electricity bills, Concur travel) and land it in **one ledger of activity records** that an analyst can review, edit, approve, and lock for reporting. Computing carbon is the easy bit; the hard parts are shape, units, missing fields, and the audit story.

## Core entities

```
organizations (1) ──< profiles ──< user_roles
              (1) ──< facility_lookups          (per-source ID → canonical facility/region)
              (1) ──< emission_factors          (kgCO2e/unit, region+year+source)
              (1) ──< ingestion_batches         (one per uploaded file)
              (1) ──< activity_records          ← the ledger; everything aggregates from here
                       └──< audit_events        (append-only; trigger-driven)
```

## `activity_records` — the single source of truth

Every row, regardless of source, has the same shape:

| Field | Why it exists |
|---|---|
| `source_system`, `source_record_id`, `source_payload` | Provenance. Lets us re-run normalization without re-asking the client. `source_payload` keeps the raw JSON of the original row. |
| `scope`, `category`, `activity_type` | GHG Protocol classification — Scope 1/2/3, then a category bucket (e.g. `purchased_electricity`), then a granular activity (`flight_long_haul`). |
| `period_start`, `period_end` | All emissions are over a window; a utility bill spans a month, a flight is a day. Modeling both lets us split across reporting periods later. |
| `facility_code`, `facility_name`, `region` | `facility_code` is the raw client identifier (a SAP WERKS code, a meter ID). `facility_name`/`region` come from `facility_lookups` and may be null on first ingest. |
| `raw_quantity`, `raw_unit` | What the source said, before normalization. Untouched. |
| `quantity`, `unit` | Canonical: `liter`, `kWh`, `passenger_km`, `room_night`. Computed at ingest. |
| `emission_factor`, `emission_factor_source` | The factor used. Stored on the row so changing the factor table tomorrow doesn't silently mutate yesterday's number. |
| `co2e_kg` | The computed number. Cached so the analyst UI doesn't recompute on every render. |
| `status` | `pending` → `needs_review` → `approved` → `locked`. Or `rejected`. |
| `flags` | Array of strings: `quantity_missing`, `unit_unrecognized`, `unmapped_facility`, `no_factor`, `outlier_high`, `period_long`. Drives the review queue. |
| `notes` | Free text from the analyst — why they accepted an estimate, etc. |
| `approved_by`, `approved_at`, `locked_at`, `edited_by`, `edited_at` | Who did what, when. |

## Why one wide table, not one table per source

Tempting to have `sap_records`, `utility_records`, `travel_records`. We rejected it:

1. The analyst's job is to review **everything that contributes to scope 1/2/3**, sorted, filtered, aggregated. A union view across three tables defeats indexes and complicates RLS.
2. Emissions math is the same shape everywhere: `quantity × factor = kg CO2e`. The differences live upstream (parser) and downstream (UI source filter), not in the storage layer.
3. New sources (a fourth utility provider, a fleet telematics feed) become a new parser, not a new table + new migrations + new UI rewrite.

The raw payload is preserved in `source_payload` (JSONB), so source-specific debugging is one column away. We get the "wide table" simplicity without losing fidelity.

## `emission_factors`

Factors are versioned by `(category, activity_type, region, valid_from)`. Lookup picks the most recent factor with `valid_from <= period_start`, region-specific first then global fallback. This means:

- A March 2025 record always uses the factor that was in force in March 2025, even if we add a 2026 update.
- An Austin electricity bill uses the US grid factor; the same record imported without a region falls back to a global average and gets the `no_factor` flag if no global exists.

## `facility_lookups`

The mapping from messy source IDs (`WERKS=1010`, `meter_id=M-104782`, traveler email) to a canonical facility name and region. Stored, not hardcoded — the analyst extends it as new IDs appear. A row without a mapping still ingests; it just gets `unmapped_facility` and waits in the review queue.

## `ingestion_batches`

One row per uploaded file. Stores filename, source, who uploaded, totals (rows total/ingested/failed). Lets the analyst answer "what did this morning's upload bring in?" without grep.

## `audit_events` and `lock`

Append-only table populated by a Postgres trigger on `activity_records`. Captures `created`, `edited`, `status_changed` with before/after JSON. Combined with a second trigger that **blocks any UPDATE on a `locked` row**, this gives us a defensible reporting story: once a number is locked into a disclosure, it cannot silently change.

## Multi-tenant + RLS

Every domain table has `organization_id` and an RLS policy that scopes it to the caller's org via a `current_org_id()` SECURITY DEFINER function. Roles (`admin`, `analyst`, `viewer`) live in a separate `user_roles` table — never on profiles, to avoid the recursive RLS / privilege-escalation trap.

## What this model does not try to be

- Not a general-purpose ETL. The shape is opinionated around emissions ledger semantics.
- Not a factor catalogue. We seed enough factors to demo; a real deployment loads from DEFRA/IEA/EPA.
- Not a reporting engine. CSR/SBTi/CDP exports are downstream of this ledger, not part of it.