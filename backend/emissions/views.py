from django.db.models import Sum, Count, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    EmissionRecord, IngestionBatch, RawRecord,
    AuditLog, RecordStatus, AuditAction, BatchStatus
)
from .serializers import (
    EmissionRecordSerializer, EmissionRecordListSerializer,
    IngestionBatchSerializer, AuditLogSerializer
)


class TenantScopedMixin:
    """All viewsets inherit this to auto-filter by request.user.tenant."""
    def get_queryset(self):
        return super().get_queryset().filter(tenant=self.request.user.tenant)


class EmissionRecordViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset         = EmissionRecord.objects.select_related("facility", "batch").prefetch_related("audit_logs")
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return EmissionRecordListSerializer
        return EmissionRecordSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        # Filters
        if scope := params.get("scope"):
            qs = qs.filter(scope=scope)
        if category := params.get("category"):
            qs = qs.filter(category=category)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if facility := params.get("facility"):
            qs = qs.filter(facility_id=facility)
        if suspicious := params.get("suspicious"):
            qs = qs.filter(is_suspicious=suspicious.lower() == "true")
        if period_start := params.get("period_start"):
            qs = qs.filter(period_start__gte=period_start)
        if period_end := params.get("period_end"):
            qs = qs.filter(period_end__lte=period_end)
        if search := params.get("search"):
            qs = qs.filter(
                Q(source_of_truth__icontains=search) |
                Q(facility__name__icontains=search) |
                Q(suspicious_reason__icontains=search)
            )
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        record = self.get_object()
        if record.status == RecordStatus.LOCKED:
            return Response({"detail": "Record is locked."}, status=status.HTTP_400_BAD_REQUEST)
        old_status = record.status
        record.status = RecordStatus.APPROVED
        record.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            emission_record=record,
            changed_by=request.user,
            action=AuditAction.APPROVE,
            old_value={"status": old_status},
            new_value={"status": RecordStatus.APPROVED},
        )
        return Response({"status": record.status})

    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        record = self.get_object()
        if record.status == RecordStatus.LOCKED:
            return Response({"detail": "Record is locked."}, status=status.HTTP_400_BAD_REQUEST)
        note = request.data.get("note", "")
        old_status = record.status
        record.status = RecordStatus.FLAGGED
        record.is_suspicious = True
        record.suspicious_reason = note
        record.save(update_fields=["status", "is_suspicious", "suspicious_reason", "updated_at"])
        AuditLog.objects.create(
            emission_record=record,
            changed_by=request.user,
            action=AuditAction.FLAG,
            old_value={"status": old_status},
            new_value={"status": RecordStatus.FLAGGED, "note": note},
        )
        return Response({"status": record.status})

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        record = self.get_object()
        if request.user.role not in ("senior_analyst", "admin"):
            return Response({"detail": "Only senior analysts can lock records."}, status=status.HTTP_403_FORBIDDEN)
        if record.status != RecordStatus.APPROVED:
            return Response({"detail": "Only approved records can be locked."}, status=status.HTTP_400_BAD_REQUEST)
        record.status = RecordStatus.LOCKED
        record.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            emission_record=record,
            changed_by=request.user,
            action=AuditAction.LOCK,
            new_value={"status": RecordStatus.LOCKED},
        )
        return Response({"status": record.status})

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Dashboard summary: totals by scope + status counts."""
        qs = self.get_queryset()
        scope_totals = (
            qs.filter(status__in=[RecordStatus.APPROVED, RecordStatus.LOCKED])
              .values("scope")
              .annotate(total_kgco2e=Sum("kgco2e"), count=Count("id"))
        )
        status_counts = (
            qs.values("status").annotate(count=Count("id"))
        )
        return Response({
            "scope_totals":  list(scope_totals),
            "status_counts": list(status_counts),
            "total_records": qs.count(),
            "suspicious":    qs.filter(is_suspicious=True).count(),
            "pending":       qs.filter(status=RecordStatus.PENDING).count(),
        })


class IngestionBatchViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset           = IngestionBatch.objects.select_related("source", "uploaded_by")
    serializer_class   = IngestionBatchSerializer
    permission_classes = [IsAuthenticated]
