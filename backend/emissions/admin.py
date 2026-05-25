from django.contrib import admin
from .models import (
    Tenant,
    Facility,
    User,
    DataSource,
    IngestionBatch,
    RawRecord,
    EmissionRecord,
    FuelDetail,
    ElectricityDetail,
    TravelDetail,
    AuditLog,
)

admin.site.register(Tenant)
admin.site.register(Facility)
admin.site.register(User)
admin.site.register(DataSource)
admin.site.register(IngestionBatch)
admin.site.register(RawRecord)
admin.site.register(EmissionRecord)
admin.site.register(FuelDetail)
admin.site.register(ElectricityDetail)
admin.site.register(TravelDetail)
admin.site.register(AuditLog)