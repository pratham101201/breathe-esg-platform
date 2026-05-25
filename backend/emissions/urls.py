from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmissionRecordViewSet, IngestionBatchViewSet

router = DefaultRouter()
router.register(r"emission-records", EmissionRecordViewSet, basename="emission-record")
router.register(r"batches",          IngestionBatchViewSet,  basename="batch")

urlpatterns = [path("api/", include(router.urls))]
