from django.urls import path
from . import views
from . import api_views


urlpatterns = [


# =====================================================
# WEB DASHBOARD
# =====================================================
path('', views.home, name='home'),
path('meters/', views.meters, name='meters'),
path('readings/', views.readings, name='readings'),
path('daily-usage-by-meter/', views.daily_usage_by_meter, name='daily_usage_by_meter'),
path('alerts/', views.alerts, name='alerts'),
path('alerts/<int:alert_id>/', views.alert_detail, name='alert_detail'),
path('reports/', views.reports, name='reports'),
path('offline-meters/', views.offline_meters, name='offline_meters'),
path('support-tickets/', views.support_tickets, name='support_tickets'),
path('support-tickets/<int:ticket_id>/', views.support_ticket_detail, name='support_ticket_detail'),
path('tariffs/', views.tariffs, name='tariffs'),
path('notifications/', views.notifications, name='notifications'),
path('audit-logs/', views.audit_logs, name='audit_logs'),
path('access-control/', views.access_control, name='access_control'),

# =====================================================
# CUSTOMER & METER MANAGEMENT
# =====================================================
path('add-water-user/', views.add_water_user, name='add_water_user'),
path('water-users/<int:user_id>/edit/', views.edit_water_user, name='edit_water_user'),
path('water-users/<int:user_id>/', views.customer_detail, name='customer_detail'),
path('meter/<int:meter_id>/', views.meter_detail, name='meter_detail'),
path('scan/meter/<str:meter_code>/', views.meter_qr_scan, name='meter_qr_scan'),
path('assigned-meter-users/', views.assigned_meter_users, name='assigned_meter_users'),
path('add-meter-for-user/<int:user_id>/', views.add_meter_for_user, name='add_meter_for_user'),
path('replace-meter/', views.replace_meter, name='replace_meter'),
path('replaced-meters/', views.replaced_meters, name='replaced_meters'),

# =====================================================
# STAFF MANAGEMENT
# =====================================================
path('add-staff/', views.add_staff, name='add_staff'),
path('staff-members/', views.staff_members, name='staff_members'),

# =====================================================
# REVENUE
# =====================================================
path('revenue-payments/', views.revenue_payments, name='revenue_payments'),

# =====================================================
# WEB AUTHENTICATION
# =====================================================
path('signup/', views.signup_view, name='signup'),
path('login/', views.login_view, name='login'),
path('logout/', views.logout_view, name='logout'),
path('forgot-account/', views.forgot_account_view, name='forgot_account'),
path('profile/photo/', views.profile_photo, name='profile_photo'),

# =====================================================
# MOBILE AUTHENTICATION API
# =====================================================
path('api/mobile/register/', api_views.mobile_register, name='mobile_register'),
path('api/mobile/login/', api_views.mobile_login, name='mobile_login'),
path('api/mobile/send-reset-code/', api_views.send_reset_code, name='send_reset_code'),
path('api/mobile/reset-password/', api_views.reset_password, name='reset_password'),

# =====================================================
# ESP32 / IOT API
# =====================================================
path('api/iot/update/', api_views.esp32_update, name='esp32_update'),

# =====================================================
# METER DATA API
# =====================================================
path('api/meter/latest/', api_views.latest_meter_reading, name='latest_meter_reading'),
path('api/meter/alerts/', api_views.meter_alerts, name='meter_alerts'),
path('api/meter/daily-usage/', api_views.daily_meter_usage, name='daily_meter_usage'),
path('api/meter/usage-chart/', api_views.usage_chart, name='usage_chart'),
path('api/meter/usage-insights/', api_views.usage_insights, name='usage_insights'),

# =====================================================
# BILLING API
# =====================================================
path('api/bill/current/', api_views.current_bill, name='current_bill'),
path('api/bill/history/', api_views.payment_history, name='payment_history'),
path('api/bill/pay/', api_views.pay_bill, name='pay_bill'),
path('api/momo/mtn/request-to-pay/', api_views.mtn_request_to_pay, name='mtn_request_to_pay'),
path('api/momo/mtn/status/<uuid:reference_id>/', api_views.mtn_payment_status, name='mtn_payment_status'),
path('api/meter/bill/', api_views.meter_bill, name='meter_bill'),

# =====================================================
# WATER CREDIT API
# =====================================================
path('api/water-credit/<str:meter_code>/',api_views.water_credit_balance,name='water_credit_balance'),

# =====================================================
# REPORTS API
# =====================================================
path('api/reports/<str:report_type>/pdf/',api_views.download_pdf_report,name='download_pdf_report'),
path('api/reports/<str:report_type>/excel/',api_views.download_excel_report,name='download_excel_report'),

# =====================================================
# SUPPORT API
# =====================================================
path('api/support/request/',api_views.create_support_request,name='create_support_request'),
path('api/notifications/',api_views.customer_notifications,name='customer_notifications'),

# =====================================================
# VALVE CONTROL API
# =====================================================
path('api/valve/status/',api_views.get_valve_status,name='get_valve_status'),
path('api/valve/control/',api_views.control_valve,name='control_valve'),]
