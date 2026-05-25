import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


# ── Enums ────────────────────────────────────────────────────────────────────

class SourceType(models.TextChoices):
    SAP      = "SAP",       "SAP Fuel & Procurement"
    UTILITY  = "UTILITY",   "Utility Electricity"
    TRAVEL   = "TRAVEL",    "Corporate Travel"

class Scope(models.IntegerChoices):
    SCOPE_1 = 1, "Scope 1"
    SCOPE_2 = 2, "Scope 2"
    SCOPE_3 = 3, "Scope 3"

class EmissionCategory(models.TextChoices):
    FUEL        = "FUEL",        "Fuel & Combustion"
    ELECTRICITY = "ELECTRICITY", "Purchased Electricity"
    TRAVEL      = "TRAVEL",      "Business Travel"

class BatchStatus(models.TextChoices):
    PENDING    = "PENDING",    "Pending"
    PROCESSING = "PROCESSING", "Processing"
    DONE       = "DONE",       "Done"
    FAILED     = "FAILED",     "Failed"

class RecordStatus(models.TextChoices):
    PENDING  = "PENDING",  "Pending Review"
    FLAGGED  = "FLAGGED",  "Flagged"
    APPROVED = "APPROVED", "Approved"
    LOCKED   = "LOCKED",   "Locked for Audit"

class AuditAction(models.TextChoices):
    EDIT    = "EDIT",    "Edited"
    APPROVE = "APPROVE", "Approved"
    FLAG    = "FLAG",    "Flagged"
    LOCK    = "LOCK",    "Locked"
    REVERT  = "REVERT",  "Reverted"

class TravelSegment(models.TextChoices):
    FLIGHT = "FLIGHT", "Flight"
    HOTEL  = "HOTEL",  "Hotel"
    GROUND = "GROUND", "Ground Transport"

class CabinClass(models.TextChoices):
    ECONOMY  = "ECONOMY",  "Economy"
    BUSINESS = "BUSINESS", "Business"
    FIRST    = "FIRST",    "First Class"

class ParseStatus(models.TextChoices):
    OK      = "OK",      "Parsed OK"
    WARNING = "WARNING", "Parsed with Warnings"
    FAILED  = "FAILED",  "Parse Failed"


# ── Tenant (multi-tenancy root) ───────────────────────────────────────────────

class Tenant(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name       = models.CharField(max_length=255)
    slug       = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant"

    def __str__(self):
        return self.name


# ── User (scoped to tenant) ───────────────────────────────────────────────────

class User(AbstractUser):
    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
    Tenant,
    on_delete=models.CASCADE,
    related_name="users",
    null=True,
    blank=True
    )
    # role controls who can lock rows (senior_analyst) vs just approve (analyst)
    ROLES = [("analyst", "Analyst"), ("senior_analyst", "Senior Analyst"), ("admin", "Admin")]
    role      = models.CharField(max_length=30, choices=ROLES, default="analyst")

    class Meta:
        db_table = "user"


# ── Facility (plant_code lookup table) ───────────────────────────────────────

class Facility(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant     = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="facilities")
    plant_code = models.CharField(max_length=10, db_index=True)   # e.g. IN01, DE03
    name       = models.CharField(max_length=255)
    country    = models.CharField(max_length=100)
    region     = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "facility"
        unique_together = [("tenant", "plant_code")]

    def __str__(self):
        return f"{self.plant_code} — {self.name}"


# ── DataSource ────────────────────────────────────────────────────────────────

class DataSource(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant      = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="data_sources")
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    name        = models.CharField(max_length=255)           # e.g. "SAP Production", "MSEDCL Portal"
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "data_source"

    def __str__(self):
        return f"{self.source_type}: {self.name}"


# ── IngestionBatch ────────────────────────────────────────────────────────────

class IngestionBatch(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant      = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="batches")
    source      = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="batches")
    facility    = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="batches", null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploads")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    filename    = models.CharField(max_length=500)
    file_hash   = models.CharField(max_length=64, blank=True)   # sha256 — detect duplicate uploads
    status      = models.CharField(max_length=20, choices=BatchStatus.choices, default=BatchStatus.PENDING)
    row_count   = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    notes       = models.TextField(blank=True)

    class Meta:
        db_table = "ingestion_batch"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.filename} ({self.status})"


# ── RawRecord — immutable source-of-truth ─────────────────────────────────────

class RawRecord(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch        = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_records")
    row_number   = models.PositiveIntegerField()                 # 1-based row in original file
    raw_data     = models.JSONField()                            # original row, verbatim
    parse_status = models.CharField(max_length=20, choices=ParseStatus.choices, default=ParseStatus.OK)
    parse_errors = models.JSONField(default=list, blank=True)    # list of error strings
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "raw_record"
        unique_together = [("batch", "row_number")]

    def __str__(self):
        return f"Row {self.row_number} of batch {self.batch_id}"


# ── EmissionRecord — core normalized table ────────────────────────────────────

class EmissionRecord(models.Model):
    id                     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant                 = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="emission_records")
    batch                  = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="emission_records")
    raw_record             = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name="emission_record", null=True)
    facility               = models.ForeignKey(Facility, on_delete=models.PROTECT, related_name="emission_records")

    # Classification
    scope                  = models.IntegerField(choices=Scope.choices)
    category               = models.CharField(max_length=20, choices=EmissionCategory.choices)

    # Activity data (original)
    activity_value         = models.DecimalField(max_digits=18, decimal_places=4)
    activity_unit          = models.CharField(max_length=20)      # L, GAL, KG, kWh, km, nights

    # Normalized energy (common aggregation unit)
    normalized_kwh         = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    # Emission calculation
    emission_factor        = models.DecimalField(max_digits=18, decimal_places=6)   # kgCO2e per unit
    emission_factor_source = models.CharField(max_length=100)                       # e.g. "DEFRA_2023"
    kgco2e                 = models.DecimalField(max_digits=18, decimal_places=4)   # activity × factor

    # Reporting period
    period_start           = models.DateField()
    period_end             = models.DateField()

    # Source-of-truth tracking
    source_of_truth        = models.CharField(max_length=500)     # e.g. "SAP:ME2M:batch_id:row_42"

    # Review workflow
    status                 = models.CharField(max_length=20, choices=RecordStatus.choices, default=RecordStatus.PENDING)
    is_edited              = models.BooleanField(default=False)   # True if analyst touched this row
    is_suspicious          = models.BooleanField(default=False)   # True if anomaly detected on ingest
    suspicious_reason      = models.TextField(blank=True)

    # Timestamps
    created_at             = models.DateTimeField(auto_now_add=True)
    updated_at             = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "emission_record"
        ordering = ["-period_start"]
        indexes  = [
            models.Index(fields=["tenant", "scope"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "period_start", "period_end"]),
            models.Index(fields=["facility"]),
        ]

    def __str__(self):
        return f"{self.category} | {self.kgco2e} kgCO2e | {self.period_start}"


# ── Source-specific detail tables ─────────────────────────────────────────────

class FuelDetail(models.Model):
    """Extra metadata for SAP fuel/procurement records."""
    emission_record = models.OneToOneField(EmissionRecord, on_delete=models.CASCADE, primary_key=True, related_name="fuel_detail")
    material_no     = models.CharField(max_length=50, blank=True)
    material_group  = models.CharField(max_length=20, blank=True)   # MATKL / Materialgruppe
    fuel_type       = models.CharField(max_length=50)               # Diesel, Petrol, LPG, HFO
    plant_code      = models.CharField(max_length=10)
    vendor_no       = models.CharField(max_length=20, blank=True)
    po_number       = models.CharField(max_length=20, blank=True)
    po_date         = models.DateField(null=True, blank=True)
    movement_type   = models.CharField(max_length=10, blank=True)   # 201, 261, etc.
    original_unit   = models.CharField(max_length=10)               # L, GAL, KG, TO as-received
    original_qty    = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        db_table = "fuel_detail"


class ElectricityDetail(models.Model):
    """Extra metadata for utility electricity records."""
    emission_record    = models.OneToOneField(EmissionRecord, on_delete=models.CASCADE, primary_key=True, related_name="electricity_detail")
    meter_no           = models.CharField(max_length=50)
    account_no         = models.CharField(max_length=50, blank=True)
    tariff_category    = models.CharField(max_length=50, blank=True)   # HT-Industry, LT-Commercial
    billing_from       = models.DateField()
    billing_to         = models.DateField()
    gross_kwh          = models.DecimalField(max_digits=18, decimal_places=4)
    solar_offset_kwh   = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    net_kwh            = models.DecimalField(max_digits=18, decimal_places=4)   # gross - solar
    grid_factor        = models.DecimalField(max_digits=10, decimal_places=6)   # kgCO2e/kWh
    grid_factor_source = models.CharField(max_length=100, default="CEA_2023")
    is_prorated        = models.BooleanField(default=False)   # True if billing period was split

    class Meta:
        db_table = "electricity_detail"


class TravelDetail(models.Model):
    """Extra metadata for corporate travel records."""
    emission_record  = models.OneToOneField(EmissionRecord, on_delete=models.CASCADE, primary_key=True, related_name="travel_detail")
    report_id        = models.CharField(max_length=50, blank=True)   # Concur report ID
    employee_id      = models.CharField(max_length=50, blank=True)
    department       = models.CharField(max_length=100, blank=True)
    segment_type     = models.CharField(max_length=10, choices=TravelSegment.choices)
    # Flight fields
    origin_iata      = models.CharField(max_length=3, blank=True)
    dest_iata        = models.CharField(max_length=3, blank=True)
    carrier          = models.CharField(max_length=10, blank=True)
    cabin_class      = models.CharField(max_length=10, choices=CabinClass.choices, blank=True)
    distance_km      = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    class_multiplier = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    # Hotel fields
    hotel_name       = models.CharField(max_length=255, blank=True)
    hotel_city       = models.CharField(max_length=100, blank=True)
    hotel_nights     = models.PositiveSmallIntegerField(null=True, blank=True)
    # Ground fields
    ground_type      = models.CharField(max_length=50, blank=True)   # Cab, Bus, Rail
    # Common
    has_receipt      = models.BooleanField(default=True)
    amount           = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency         = models.CharField(max_length=3, blank=True)

    class Meta:
        db_table = "travel_detail"


# ── AuditLog — immutable change history ───────────────────────────────────────

class AuditLog(models.Model):
    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    emission_record   = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name="audit_logs")
    changed_by        = models.ForeignKey(User, on_delete=models.PROTECT, related_name="audit_logs")
    changed_at        = models.DateTimeField(auto_now_add=True)
    action            = models.CharField(max_length=20, choices=AuditAction.choices)
    old_value         = models.JSONField(null=True, blank=True)   # snapshot before change
    new_value         = models.JSONField(null=True, blank=True)   # snapshot after change
    note              = models.TextField(blank=True)

    class Meta:
        db_table  = "audit_log"
        ordering  = ["-changed_at"]

    def __str__(self):
        return f"{self.action} by {self.changed_by} on {self.emission_record_id}"
