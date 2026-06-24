from django.contrib import admin
from .models import (
    WaterUser,
    Meter,
    Reading,
    Alert,
    SupportRequest,
    Bill,
    Payment,
    UserProfile,
    MobileMoneyTransaction,
)

admin.site.register(WaterUser)
admin.site.register(Meter)
admin.site.register(Reading)
admin.site.register(Alert)
admin.site.register(SupportRequest)
admin.site.register(Bill)
admin.site.register(Payment)
admin.site.register(UserProfile)
admin.site.register(MobileMoneyTransaction)
