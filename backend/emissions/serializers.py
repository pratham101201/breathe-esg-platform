from rest_framework import serializers
from .models import (
    Tenant, Facility, DataSource, IngestionBatch,
    RawRecord, EmissionRecord, FuelDetail, ElectricityDetail,
    TravelDetail, AuditLog, User
)


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Facility
        fields = ["id", "plant_code", "name", "country", "region"]


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DataSource
        fields = ["id", "source_type", "name"]


class IngestionBatchSerializer(serializers.ModelSerializer):
    source_name      = serializers.CharField(source="source.name", read_only=True)
    source_type      = serializers.CharField(source="source.source_type", read_only=True)
    uploaded_by_name = serializers.CharField(source="uploaded_by.get_full_name", read_only=True)

    class Meta:
        model  = IngestionBatch
        fields = [
            "id", "source_name", "source_type", "uploaded_by_name",
            "uploaded_at", "filename", "status", "row_count", "error_count", "notes"
        ]


class FuelDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model  = FuelDetail
        exclude = ["emission_record"]


class ElectricityDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ElectricityDetail
        exclude = ["emission_record"]


class TravelDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TravelDetail
        exclude = ["emission_record"]


class AuditLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.get_full_name", read_only=True)

    class Meta:
        model  = AuditLog
        fields = ["id", "changed_by_name", "changed_at", "action", "old_value", "new_value", "note"]


class EmissionRecordSerializer(serializers.ModelSerializer):
    facility_name   = serializers.CharField(source="facility.name", read_only=True)
    fuel_detail     = FuelDetailSerializer(read_only=True)
    electricity_detail = ElectricityDetailSerializer(read_only=True)
    travel_detail   = TravelDetailSerializer(read_only=True)
    audit_logs      = AuditLogSerializer(many=True, read_only=True)
    batch_filename  = serializers.CharField(source="batch.filename", read_only=True)

    class Meta:
        model  = EmissionRecord
        fields = [
            "id", "facility", "facility_name", "scope", "category",
            "activity_value", "activity_unit", "normalized_kwh",
            "emission_factor", "emission_factor_source", "kgco2e",
            "period_start", "period_end", "source_of_truth",
            "status", "is_edited", "is_suspicious", "suspicious_reason",
            "created_at", "updated_at", "batch_filename",
            "fuel_detail", "electricity_detail", "travel_detail", "audit_logs"
        ]


class EmissionRecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for dashboard list view — no nested details."""
    facility_name = serializers.CharField(source="facility.name", read_only=True)

    class Meta:
        model  = EmissionRecord
        fields = [
            "id", "facility_name", "scope", "category",
            "activity_value", "activity_unit", "kgco2e",
            "period_start", "period_end", "status",
            "is_edited", "is_suspicious", "created_at"
        ]
