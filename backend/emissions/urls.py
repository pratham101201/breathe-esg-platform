from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmissionRecordViewSet, IngestionBatchViewSet, DataSourceViewSet, FacilityViewSet, AuditLogViewSet, RawRecordViewSet

router = DefaultRouter()
router.register(r"emission-records", EmissionRecordViewSet, basename="emission-record")
router.register(r"batches",          IngestionBatchViewSet,  basename="batch")
router.register(r"data-sources",    DataSourceViewSet,     basename="data-source")
router.register(r"facilities",       FacilityViewSet,       basename="facility")
router.register(r"audit-logs",      AuditLogViewSet,      basename="audit-log")
router.register(r"raw-records",    RawRecordViewSet,     basename="raw-record")
urlpatterns = [path("api/", include(router.urls))]
