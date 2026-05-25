# Sources

How each of the three sources was modeled, what assumptions were made, and what real-world quirks the parser handles.

---

## 1. SAP — fuel and natural gas

### Why this shape

SAP exposes data through several channels: IDoc (XML messages), OData (REST on S/4HANA), BAPI/RFC (binary RPC over SAP GUI), and flat-file exports from transactions like `SE16N`, `MB51`, `ME2N`. We chose **flat-file CSV** because:

- It's what 80% of mid-market SAP customers actually share. OData requires S/4HANA + IT involvement; IDoc requires middleware (PI/PO or CPI). A sustainability lead who can run `SE16N` and click "Export" is the realistic ingest path.
- The CSV format is stable across SAP versions; OData endpoints change between releases.
- It models the "messy export emailed to the analyst" reality the PM described.

### What we accept

SE16N-style CSV with German headers (the SAP defaults). Required columns:

| Column | Meaning |
|---|---|
| `WERKS` | Plant code (used as `facility_code`) |
| `MATNR` | Material number |
| `MAKTX` | Material description (used to classify into diesel/petrol/natural gas) |
| `MENGE` | Quantity |
| `MEINS` | Unit of measure (`L`, `GAL`, `M3`, …) |
| `BUDAT` | Posting date |
| `EBELN` | Purchasing document (used for dedup id) |

### Real-world quirks handled

1. **German decimal commas.** `1.500,000` → `1500.000`. Auto-detected: if both `.` and `,` present, `.` is treated as thousands separator.
2. **German date format.** `15.03.2025` → `2025-03-15`. ISO and US formats also accepted.
3. **Semicolon delimiter.** German locale Excel defaults to `;`; the parser sniffs the header line.
4. **Mixed units in one file.** A multi-plant export has `L` from Frankfurt and `GAL` from Houston. Normalized to liters; `M3` for `ERDGAS` lines normalized to kWh.
5. **Material descriptions in mixed languages.** Classification matches `DIESEL`, `BENZIN`, `PETROL`, `GASOLINE`, `ERDGAS`, `NATURAL GAS` case-insensitively on `MAKTX`.
6. **Non-fuel rows.** `Office Paper A4` falls through classification and is logged as skipped — not ingested, not silently misclassified.

### Assumptions

- Plant codes (`WERKS`) are stable identifiers a client maintains in `facility_lookups`. The first time a new `WERKS` appears, the row ingests with `unmapped_facility` and the analyst extends the lookup table once.
- Material number alone is not used for classification — descriptions are more portable across SAP installations.

---

## 2. Utility — purchased electricity

### Why this shape

Utility data comes in three realistic channels:
- Portal CSV downloads (every commercial utility provides one).
- PDF bills (the analyst hand-keys, or we OCR).
- Green Button XML (US-only, requires customer authorization with each utility).

We chose **portal CSV** because it's the only path that works across geographies on day one and doesn't require OCR. PDF and Green Button are valuable next steps; both feed the same `activity_records` table once parsed, so adding them is parser work, not modeling work.

### What we accept

CSV with the columns most US/EU portals expose:

| Column | Meaning |
|---|---|
| `meter_id` | Used as `facility_code` |
| `billing_period_start`, `billing_period_end` | The bill window |
| `usage_kwh` | Quantity |
| `service_address` | Used to infer region (US/IN/DE) if no facility mapping exists |
| `tariff`, `charge_total_usd` | Stored in `source_payload` for context, not used for emissions |

### Real-world quirks handled

1. **Missing usage on demand-only meters.** Some industrial bills report only kW demand for some periods. Ingested with `quantity_missing` flag; analyst can add a manual reading.
2. **Service addresses in any format.** Region inference is heuristic (string matching on country/state tokens) — when it fails, the row falls back to global average and gets `no_factor` or uses whatever the `facility_lookups` mapping provides.
3. **Multiple meters per account.** Each meter becomes its own row; the `(meter_id, period_start, period_end)` triple is the dedup key.
4. **Empty cost fields.** Cost is not part of emissions math — kept in `source_payload` but not required.

### Assumptions

- We use grid-average emission factors per region (US/EU/IN), not residual-mix or contractual instruments (RECs, GOs, PPAs). Market-based reporting is a separate scope and a separate factor table — explicitly deferred.
- One meter maps to one facility. Sub-metering allocation across cost centers is out of scope.

---

## 3. Concur — business travel

### Why this shape

Concur exposes data through:
- Concur v4 REST (`/api/v4.0/travel/itinerary`) — the modern, documented path.
- Older v3 SOAP — deprecated.
- TMC-direct CSV exports — varies by travel manager.

We chose **v4 itinerary JSON** because the schema is stable, documented, and matches what the Concur SDK returns. CSV exports vary by TMC and would mean writing one parser per Concur reseller.

### What we accept

JSON in the v4 itinerary shape:

```json
{ "items": [{
  "tripId": "TRP-...",
  "travelerEmail": "...",
  "segments": [
    { "type": "air",    "from": "BLR", "to": "DEL", "departure": "...", "distanceKm": 1740 },
    { "type": "hotel",  "checkIn": "...", "checkOut": "...", "nights": 2 },
    { "type": "ground", "subType": "taxi", "distanceKm": 22, "date": "..." }
  ]
}]}
```

### Real-world quirks handled

1. **Missing `distanceKm` on flights.** Concur sometimes omits this on codeshare or low-cost carriers. We look up a small `from-to` airport-pair distance table and flag `distance_estimated`. If the pair is unknown, flag `distance_missing` and skip the segment (not the whole trip).
2. **Cabin class without factor.** Captured in `source_payload`. Today's classifier buckets by haul (`flight_domestic` ≤ 800km, `flight_short_haul` ≤ 3700km, `flight_long_haul` > 3700km) and ignores cabin. A premium-cabin upgrade is a deliberate next step.
3. **Hotel night counting.** Trust the source's `nights`; fall back to `checkOut - checkIn` if missing (not yet implemented — flagged).
4. **Ground transport modes.** `taxi` and `rail` recognized; `rental_car` and `rideshare` fall through to `taxi` with a flag (today; would split factor tomorrow).
5. **Traveler identity.** Stored as `facility_code` (the traveler email). This is a small abuse of the field, but it lets the analyst filter "all of Akhil's trips" without a separate `traveler` table on day one.

### Assumptions

- The traveler is an employee of the org, so the trip is Scope 3 cat 6 (business travel). Vendor or contractor travel is not separated.
- Distances are great-circle, not actual routed. Concur reports vary; we use what the source provides.
- Radiative forcing multiplier (often 1.9× for high-altitude flights) is NOT applied automatically — captured in the factor table per activity if desired. This is a contested methodology question and we don't want to silently inflate numbers.

---

## What's missing on purpose

- **Refrigerants, waste, water, fugitive emissions** — these have small numbers and big modeling overhead. Out of scope.
- **Procurement-based Scope 3 (cat 1)** — would need spend-based emission factors and a category mapping per cost center. Worth its own ingestion path, not a footnote here.
- **Real-time API ingestion** — today the parsers accept file uploads. Webhooks/cron pulls are the same parser wrapped in a scheduler.