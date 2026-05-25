"""
Ingestion pipeline — one class per source type.
Each ingester:
  1. Reads raw bytes / CSV
  2. Creates RawRecord per row (verbatim)
  3. Normalizes → creates EmissionRecord + detail table
  4. Flags anomalies
"""
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime
from decimal import Decimal

import chardet

from .models import (
    IngestionBatch, RawRecord, EmissionRecord,
    FuelDetail, ElectricityDetail, TravelDetail,
    Scope, EmissionCategory, BatchStatus, ParseStatus,
    TravelSegment, CabinClass
)

# ── Emission factors (DEFRA 2023, CEA 2023) ───────────────────────────────────
FUEL_FACTORS = {
    "DIESEL": Decimal("2.68"),   # kgCO2e/litre
    "PETROL": Decimal("2.31"),
    "LPG":    Decimal("1.56"),   # kgCO2e/kg
    "HFO":    Decimal("3.21"),   # kgCO2e/kg
    "CNG":    Decimal("2.04"),   # kgCO2e/kg
}
FUEL_CALORIFIC = {   # MJ/litre for kWh conversion (1 MJ = 0.2778 kWh)
    "DIESEL": Decimal("35.8"),
    "PETROL": Decimal("32.2"),
    "LPG":    Decimal("25.3"),
    "HFO":    Decimal("40.0"),
}
GRID_FACTOR_INDIA = Decimal("0.82")     # kgCO2e/kWh, CEA 2023
FLIGHT_SHORT_HAUL = Decimal("0.255")    # kgCO2e/km, <1500km
FLIGHT_LONG_HAUL  = Decimal("0.195")   # kgCO2e/km, >1500km
FLIGHT_THRESHOLD_KM = 1500
CLASS_MULTIPLIER  = {"ECONOMY": Decimal("1.0"), "BUSINESS": Decimal("2.0"), "FIRST": Decimal("4.0")}
HOTEL_FACTOR_INDIA = Decimal("20.6")   # kgCO2e/night
TAXI_FACTOR        = Decimal("0.21")   # kgCO2e/km

# German → English SAP header mapping
SAP_HEADER_MAP = {
    "einkaufsorg.": "purchasing_org",
    "werk":         "plant_code",
    "lieferant":    "vendor_no",
    "material":     "material_no",
    "kurztext":     "description",
    "menge":        "quantity",
    "me":           "unit",
    "nettopreis":   "net_price",
    "waehrung":     "currency",
    "bestelldatum": "po_date",
    "belegdatum":   "document_date",
    "materialgruppe": "material_group",
}

MATERIAL_GROUP_TO_FUEL = {
    "FUEL-D": "DIESEL",
    "FUEL-P": "PETROL",
    "FUEL-G": "LPG",
    "FUEL-H": "HFO",
    "FUEL-C": "CNG",
}

UNIT_CONVERSIONS = {
    # to litres
    "GAL": Decimal("3.78541"),
    "L":   Decimal("1"),
    "ML":  Decimal("0.001"),
    # to kg
    "KG":  Decimal("1"),
    "TO":  Decimal("1000"),
    "G":   Decimal("0.001"),
    "M3":  Decimal("0.8"),      # approximate for diesel
}


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            pass
    return None


def detect_encoding(raw_bytes: bytes) -> str:
    result = chardet.detect(raw_bytes)
    return result.get("encoding") or "utf-8"


def file_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


# ── SAP Fuel Ingester ─────────────────────────────────────────────────────────

class SAPFuelIngester:
    def ingest(self, batch: IngestionBatch, raw_bytes: bytes, facility_lookup: dict):
        encoding = detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding, errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=",")

        batch.file_hash = file_hash(raw_bytes)
        batch.status = BatchStatus.PROCESSING
        batch.save(update_fields=["file_hash", "status"])

        ok = errors = 0
        for i, row in enumerate(reader, start=1):
            # Normalize headers (handle German)
            row = {SAP_HEADER_MAP.get(k.lower().strip(), k.lower().strip()): v.strip() for k, v in row.items()}
            raw_record = RawRecord.objects.create(
                batch=batch, row_number=i, raw_data=row
            )
            try:
                self._process_row(raw_record, row, batch, facility_lookup)
                ok += 1
            except Exception as e:
                raw_record.parse_status = ParseStatus.FAILED
                raw_record.parse_errors = [str(e)]
                raw_record.save(update_fields=["parse_status", "parse_errors"])
                errors += 1

        batch.row_count = ok + errors
        batch.error_count = errors
        batch.status = BatchStatus.DONE if errors == 0 else BatchStatus.FAILED
        batch.save(update_fields=["row_count", "error_count", "status"])

    def _process_row(self, raw_record, row, batch, facility_lookup):
        plant_code  = row.get("plant_code", "").strip()
        mat_group   = row.get("material_group", "").strip().upper()
        fuel_type   = MATERIAL_GROUP_TO_FUEL.get(mat_group, "DIESEL")
        unit        = row.get("unit", "L").strip().upper()
        qty_raw     = row.get("quantity", "0").replace(",", ".")
        qty         = Decimal(qty_raw) if qty_raw else Decimal("0")
        po_date     = parse_date(row.get("po_date", ""))
        doc_date    = parse_date(row.get("document_date", ""))
        period      = po_date or doc_date or date.today()

        # Unit → litres or kg
        conversion  = UNIT_CONVERSIONS.get(unit, Decimal("1"))
        std_qty     = qty * conversion
        std_unit    = "L" if unit in ("GAL", "L", "ML", "M3") else "KG"

        factor      = FUEL_FACTORS.get(fuel_type, Decimal("2.68"))
        kgco2e      = std_qty * factor
        calorific   = FUEL_CALORIFIC.get(fuel_type)
        norm_kwh    = (std_qty * calorific * Decimal("0.2778")) if calorific else None

        facility    = facility_lookup.get(plant_code)
        suspicious  = qty == 0 or not po_date or not mat_group
        sus_reason  = []
        if qty == 0:     sus_reason.append("Zero quantity")
        if not po_date:  sus_reason.append("Missing PO date")
        if not mat_group: sus_reason.append("Missing material group")

        er = EmissionRecord.objects.create(
            tenant=batch.tenant,
            batch=batch,
            raw_record=raw_record,
            facility=facility or batch.facility,
            scope=Scope.SCOPE_1,
            category=EmissionCategory.FUEL,
            activity_value=std_qty,
            activity_unit=std_unit,
            normalized_kwh=norm_kwh,
            emission_factor=factor,
            emission_factor_source="DEFRA_2023",
            kgco2e=kgco2e,
            period_start=period,
            period_end=period,
            source_of_truth=f"SAP:ME2M:{batch.id}:row_{raw_record.row_number}",
            is_suspicious=suspicious,
            suspicious_reason="; ".join(sus_reason),
        )
        FuelDetail.objects.create(
            emission_record=er,
            material_no=row.get("material_no", ""),
            material_group=mat_group,
            fuel_type=fuel_type,
            plant_code=plant_code,
            vendor_no=row.get("vendor_no", ""),
            po_number=row.get("po_number", ""),
            po_date=po_date,
            movement_type=row.get("movement_type", ""),
            original_unit=unit,
            original_qty=qty,
        )


# ── Utility Electricity Ingester ──────────────────────────────────────────────

class UtilityElectricityIngester:
    def ingest(self, batch: IngestionBatch, raw_bytes: bytes, meter_lookup: dict):
        encoding = detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding, errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        batch.file_hash = file_hash(raw_bytes)
        batch.status = BatchStatus.PROCESSING
        batch.save(update_fields=["file_hash", "status"])
        ok = errors = 0
        for i, row in enumerate(reader, start=1):
            row = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items()}
            raw_record = RawRecord.objects.create(batch=batch, row_number=i, raw_data=row)
            try:
                self._process_row(raw_record, row, batch, meter_lookup)
                ok += 1
            except Exception as e:
                raw_record.parse_status = ParseStatus.FAILED
                raw_record.parse_errors = [str(e)]
                raw_record.save(update_fields=["parse_status", "parse_errors"])
                errors += 1
        batch.row_count = ok + errors
        batch.error_count = errors
        batch.status = BatchStatus.DONE if errors == 0 else BatchStatus.FAILED
        batch.save(update_fields=["row_count", "error_count", "status"])

    def _process_row(self, raw_record, row, batch, meter_lookup):
        meter_no   = row.get("meter_no", "")
        billing_from = parse_date(row.get("billing_from", ""))
        billing_to   = parse_date(row.get("billing_to", ""))
        gross_raw  = row.get("units_kwh", row.get("gross_kwh", "0")).replace(",", "")
        solar_raw  = row.get("solar_offset_kwh", "0").replace(",", "") or "0"
        gross_kwh  = Decimal(gross_raw) if gross_raw else Decimal("0")
        solar_kwh  = Decimal(solar_raw)
        net_kwh    = gross_kwh - solar_kwh

        # Pro-rate if billing period spans multiple months
        is_prorated = False
        if billing_from and billing_to:
            if billing_from.month != billing_to.month or billing_from.year != billing_to.year:
                is_prorated = True

        kgco2e = net_kwh * GRID_FACTOR_INDIA
        facility = meter_lookup.get(meter_no) or batch.facility
        suspicious = gross_kwh == 0 or not billing_from
        sus_reason = []
        if gross_kwh == 0: sus_reason.append("Zero consumption")
        if not billing_from: sus_reason.append("Missing billing date")

        er = EmissionRecord.objects.create(
            tenant=batch.tenant, batch=batch, raw_record=raw_record,
            facility=facility,
            scope=Scope.SCOPE_2,
            category=EmissionCategory.ELECTRICITY,
            activity_value=net_kwh,
            activity_unit="kWh",
            normalized_kwh=net_kwh,
            emission_factor=GRID_FACTOR_INDIA,
            emission_factor_source="CEA_2023",
            kgco2e=kgco2e,
            period_start=billing_from or date.today(),
            period_end=billing_to or date.today(),
            source_of_truth=f"UTILITY:CSV:{batch.id}:row_{raw_record.row_number}",
            is_suspicious=suspicious,
            suspicious_reason="; ".join(sus_reason),
        )
        ElectricityDetail.objects.create(
            emission_record=er,
            meter_no=meter_no,
            account_no=row.get("account_no", ""),
            tariff_category=row.get("tariff", ""),
            billing_from=billing_from or date.today(),
            billing_to=billing_to or date.today(),
            gross_kwh=gross_kwh,
            solar_offset_kwh=solar_kwh,
            net_kwh=net_kwh,
            grid_factor=GRID_FACTOR_INDIA,
            grid_factor_source="CEA_2023",
            is_prorated=is_prorated,
        )


# ── Corporate Travel Ingester ─────────────────────────────────────────────────

# Static IATA lookup (lat, lon) — top 20 Indian + common international airports
IATA_COORDS = {
    "BOM": (19.0896, 72.8656), "DEL": (28.5562, 77.1000), "MAA": (12.9941, 80.1709),
    "BLR": (13.1986, 77.7066), "CCU": (22.6547, 88.4467), "HYD": (17.2403, 78.4294),
    "COK": (10.1520, 76.4019), "AMD": (23.0771, 72.6347), "PNQ": (18.5822, 73.9197),
    "LHR": (51.4775, -0.4614), "JFK": (40.6413, -73.7781), "DXB": (25.2528, 55.3644),
    "SIN": (1.3644, 103.9915), "HKG": (22.3080, 113.9185), "CDG": (49.0097, 2.5479),
    "FRA": (50.0333, 8.5706),  "NRT": (35.7720, 140.3929), "SYD": (-33.9399, 151.1753),
}

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))

CABIN_MAP = {
    "y": "ECONOMY", "eco": "ECONOMY", "economy": "ECONOMY",
    "c": "BUSINESS", "j": "BUSINESS", "business": "BUSINESS",
    "f": "FIRST", "first": "FIRST", "first class": "FIRST",
}

class CorporateTravelIngester:
    def ingest(self, batch: IngestionBatch, raw_bytes: bytes):
        encoding = detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding, errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        batch.file_hash = file_hash(raw_bytes)
        batch.status = BatchStatus.PROCESSING
        batch.save(update_fields=["file_hash", "status"])
        ok = errors = 0
        for i, row in enumerate(reader, start=1):
            row = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items()}
            raw_record = RawRecord.objects.create(batch=batch, row_number=i, raw_data=row)
            try:
                self._process_row(raw_record, row, batch)
                ok += 1
            except Exception as e:
                raw_record.parse_status = ParseStatus.FAILED
                raw_record.parse_errors = [str(e)]
                raw_record.save(update_fields=["parse_status", "parse_errors"])
                errors += 1
        batch.row_count = ok + errors
        batch.error_count = errors
        batch.status = BatchStatus.DONE if errors == 0 else BatchStatus.FAILED
        batch.save(update_fields=["row_count", "error_count", "status"])

    def _process_row(self, raw_record, row, batch):
        seg_raw  = row.get("segment_type", "FLIGHT").strip().upper()
        segment  = seg_raw if seg_raw in ("FLIGHT", "HOTEL", "GROUND") else "FLIGHT"
        travel_date = parse_date(row.get("travel_date", "")) or date.today()
        return_date = parse_date(row.get("return_date", "")) or travel_date
        has_receipt = row.get("receipt", "Y").strip().upper() != "N"
        amount_raw  = row.get("amount", "0").replace(",", "").replace(" ", "") or "0"
        amount      = Decimal(amount_raw)
        currency    = row.get("currency", "INR")

        kgco2e = Decimal("0")
        distance_km = None
        cabin_class = "ECONOMY"
        class_mult  = Decimal("1.0")
        nights      = None

        if segment == "FLIGHT":
            origin = row.get("origin", "").upper()
            dest   = row.get("destination", row.get("dest", "")).upper()
            cabin_raw = row.get("class", "economy").strip().lower()
            cabin_class = CABIN_MAP.get(cabin_raw, "ECONOMY")
            class_mult  = CLASS_MULTIPLIER[cabin_class]

            if origin in IATA_COORDS and dest in IATA_COORDS:
                o, d_ = IATA_COORDS[origin], IATA_COORDS[dest]
                distance_km = Decimal(str(round(haversine_km(*o, *d_), 2)))
            else:
                distance_km = Decimal("0")

            base_factor = FLIGHT_SHORT_HAUL if float(distance_km or 0) < FLIGHT_THRESHOLD_KM else FLIGHT_LONG_HAUL
            kgco2e = distance_km * base_factor * class_mult if distance_km else Decimal("0")
            factor = base_factor
            factor_src = "DEFRA_2023_FLIGHT"

        elif segment == "HOTEL":
            checkin  = parse_date(row.get("travel_date", "")) or travel_date
            checkout = parse_date(row.get("return_date", "")) or return_date
            nights   = max((checkout - checkin).days, 1)
            kgco2e   = Decimal(nights) * HOTEL_FACTOR_INDIA
            factor   = HOTEL_FACTOR_INDIA
            factor_src = "DEFRA_2023_HOTEL"

        else:  # GROUND
            dist_raw = row.get("distance_km", "0").replace(",", "") or "0"
            distance_km = Decimal(dist_raw) if dist_raw else Decimal("20")  # estimate if missing
            kgco2e = distance_km * TAXI_FACTOR
            factor = TAXI_FACTOR
            factor_src = "DEFRA_2023_GROUND"

        # Anomaly detection
        suspicious = not has_receipt or (amount > 50000)
        sus_reason = []
        if not has_receipt: sus_reason.append("No receipt")
        if amount > 50000:  sus_reason.append(f"High amount {amount} {currency}")

        er = EmissionRecord.objects.create(
            tenant=batch.tenant, batch=batch, raw_record=raw_record,
            facility=batch.facility,
            scope=Scope.SCOPE_3,
            category=EmissionCategory.TRAVEL,
            activity_value=distance_km or Decimal(nights or 1),
            activity_unit="km" if segment != "HOTEL" else "nights",
            normalized_kwh=None,
            emission_factor=factor,
            emission_factor_source=factor_src,
            kgco2e=kgco2e,
            period_start=travel_date,
            period_end=return_date,
            source_of_truth=f"TRAVEL:CONCUR:{batch.id}:row_{raw_record.row_number}",
            is_suspicious=suspicious,
            suspicious_reason="; ".join(sus_reason),
        )
        TravelDetail.objects.create(
            emission_record=er,
            report_id=row.get("report_id", ""),
            employee_id=row.get("employee_id", ""),
            department=row.get("dept", row.get("department", "")),
            segment_type=segment,
            origin_iata=row.get("origin", ""),
            dest_iata=row.get("destination", row.get("dest", "")),
            carrier=row.get("carrier", ""),
            cabin_class=cabin_class,
            distance_km=distance_km,
            class_multiplier=class_mult,
            hotel_name=row.get("hotel_name", ""),
            hotel_city=row.get("hotel_city", ""),
            hotel_nights=nights,
            ground_type=row.get("ground_type", ""),
            has_receipt=has_receipt,
            amount=amount,
            currency=currency,
        )
