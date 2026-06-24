from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Alert
from datetime import timedelta


import random
from functools import wraps

from .forms import (
    MeterForm,
    WaterUserForm,
    ExtraMeterForm,
    MeterReplacementForm,
    StaffForm,
    AlertWorkflowForm,
    SupportWorkflowForm,
    TariffForm,
    NotificationForm,
    UserRoleForm,
    ProfilePhotoForm,
)

from .models import (
    Meter,
    WaterUser,
    StaffMember,
    MeterReplacement,
    Payment,
    Reading,
    Bill,
    SupportRequest,
    Tariff,
    Notification,
    AuditLog,
    ValveActivity,
    UserProfile,
)
from .permissions import user_has_permission


OFFLINE_AFTER_HOURS = 24


def meter_rate(meter):
    if meter.tariff and meter.tariff.active:
        return float(meter.tariff.rate_per_litre)
    return 5.0


def estimated_reading_cost(readings):
    grouped = list(readings.values('meter_id').annotate(total=Sum('usage_litres')))
    meters = {
        meter.id: meter
        for meter in Meter.objects.select_related('tariff').filter(
            id__in=[row['meter_id'] for row in grouped]
        )
    }
    return sum(
        float(row['total'] or 0) * meter_rate(meters[row['meter_id']])
        for row in grouped
        if row['meter_id'] in meters
    )


def record_audit(request, action, instance, description):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        entity_type=instance.__class__.__name__,
        entity_id=str(instance.pk or ''),
        description=description,
        ip_address=request.META.get('REMOTE_ADDR'),
    )


def roles_allowed(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if profile.role not in roles:
                messages.error(request, "Your role does not allow access to that page.")
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def permission_required(permission):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not user_has_permission(request.user, permission):
                messages.error(request, "Your role does not allow access to that page.")
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator

# =====================================================
# BASE CONTEXT (REAL DATABASE DATA ONLY)
# =====================================================
def base_context():
    today = now().date()

    total_meters = Meter.objects.count()
    offline_cutoff = now() - timedelta(hours=OFFLINE_AFTER_HOURS)
    offline_meters = Meter.objects.filter(
        Q(last_seen__lt=offline_cutoff) |
        Q(last_seen__isnull=True, date_assigned__lt=offline_cutoff)
    ).count()
    active_meters = total_meters - offline_meters
    open_alerts = Alert.objects.exclude(status="Resolved").count()

    today_usage = Reading.objects.filter(
        reading_date=today
    ).aggregate(total=Sum("usage_litres"))["total"] or 0

    meters = Meter.objects.select_related("user").all()
    recent_meters = meters.order_by("-date_assigned", "-id")[:5]

    meter_rows = [
        {
            "id": m.id,
            "code": m.meter_code,
            "location": m.location,
            "owner": m.user.full_name if m.user else "Unassigned",
            "status": m.effective_status,
        }
        for m in recent_meters
    ]

    recent_payments = Payment.objects.select_related('bill').order_by('-paid_at')[:5]

    # 🔥 ADD THIS (IMPORTANT)
    recent_readings = Reading.objects.order_by("-id")[:10]

    reading_rows = [
        {
            "meter": r.meter.meter_code,
            "reading_date": r.reading_date,
            "usage_litres": r.usage_litres,
        }
        for r in recent_readings
    ]

    usage_totals = {
        row["meter_id"]: row["total"] or 0
        for row in Reading.objects.filter(reading_date=today)
        .values("meter_id")
        .annotate(total=Sum("usage_litres"))
    }

    daily_meter_usage_rows = [
        {
            "meter": m.meter_code,
            "location": m.location,
            "owner": m.user.full_name if m.user else "Unassigned",
            "usage": usage_totals.get(m.id, 0),
        }
        for m in meters
    ]

    alerts = Alert.objects.all().order_by('-id')[:10]
    
    alert_rows = [
    {
        "meter": a.meter.meter_code,
        "type": a.alert_type,
        "severity": a.severity,
        "time": a.created_at,
    }
    for a in alerts
]

    return {
        "total_meters": total_meters,
        "active_meters": active_meters,
        "offline_meters": offline_meters,
        "open_alerts": open_alerts,
        "today_usage": today_usage,
        "meter_rows": meter_rows,
        "daily_meter_usage_rows": daily_meter_usage_rows,
        "recent_payments": recent_payments,
        "reading_rows": reading_rows,   # 🔥 ADD
        "alert_rows": alert_rows,       # 🔥 ADD
    }


@api_view(['GET'])
def dashboard_summary(request):

    recent_readings = Reading.objects.select_related("meter").order_by("-id")[:10]

    reading_rows = [
        {
            "meter": r.meter.meter_code,
            "day": r.reading_date,
            "usage": r.usage_litres,
        }
        for r in recent_readings
    ]

    return Response({
        "summary": {},
        "meter_rows": [],
        "reading_rows": reading_rows,
        "recent_payments": []
    })


# =====================================================
# DASHBOARD PAGES
# =====================================================
@login_required(login_url='login')
@permission_required('dashboard')
def home(request):
    context = base_context()
    context['page_title'] = 'Water Regulator Dashboard'
    return render(request, 'dashboard/home.html', context)


@login_required(login_url='login')
@permission_required('readings')
def readings(request):

    recent_readings = Reading.objects.select_related("meter").order_by("-id")

    reading_rows = [
        {
            "meter": r.meter.meter_code,
            "day": r.reading_date,
            "usage": r.usage_litres,
        }
        for r in recent_readings
    ]

    context = base_context()
    context["reading_rows"] = reading_rows
    context["page_title"] = "Water Readings"

    return render(request, "dashboard/readings.html", context)


@login_required(login_url='login')
@permission_required('readings')
def daily_usage_by_meter(request):
    context = base_context()
    context["active_usage_meters"] = sum(
        1 for row in context["daily_meter_usage_rows"]
        if row["usage"] > 0
    )
    context["page_title"] = "Daily Usage By Meter"
    return render(request, "dashboard/daily_usage_by_meter.html", context)


@login_required(login_url='login')
@permission_required('alerts')
def alerts(request):
    alert_list = Alert.objects.select_related('meter', 'assigned_to').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    severity = request.GET.get('severity', '')
    query = request.GET.get('q', '').strip()
    if status_filter:
        alert_list = alert_list.filter(status=status_filter)
    if severity:
        alert_list = alert_list.filter(severity=severity)
    if query:
        alert_list = alert_list.filter(
            Q(meter__meter_code__icontains=query) | Q(alert_type__icontains=query)
        )
    context = base_context()
    context['alerts'] = alert_list
    context['status_filter'] = status_filter
    context['severity_filter'] = severity
    context['query'] = query
    context['page_title'] = 'Alerts'
    return render(request, 'dashboard/alerts.html', context)


@login_required(login_url='login')
@permission_required('alerts_manage')
def alert_detail(request, alert_id):
    alert = get_object_or_404(Alert, id=alert_id)
    if request.method == 'POST':
        form = AlertWorkflowForm(request.POST, instance=alert)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.resolved_at = now() if alert.status == 'Resolved' else None
            alert.save()
            record_audit(request, 'Updated alert', alert, f"Alert marked {alert.status}")
            messages.success(request, "Alert workflow updated.")
            return redirect('alerts')
    else:
        form = AlertWorkflowForm(instance=alert)
    return render(request, 'dashboard/workflow_form.html', {
        'form': form, 'record': alert, 'page_title': 'Alert Workflow',
        'heading': f'{alert.meter.meter_code}: {alert.alert_type}',
        'back_url': 'alerts',
    })


@login_required(login_url='login')
@permission_required('reports')
def reports(request):
    context = base_context()
    today = now().date()

    report_defs = [
        {
            "title": "Daily Usage Report",
            "type": "daily",
            "period": today.strftime("%d %b %Y"),
            "icon": "fa-calendar-check-o",
        },
        {
            "title": "Weekly Usage Report",
            "type": "weekly",
            "period": f"{today - timedelta(days=6):%d %b %Y} - {today:%d %b %Y}",
            "icon": "fa-calendar",
        },
        {
            "title": "Monthly Usage Report",
            "type": "monthly",
            "period": today.strftime("%B %Y"),
            "icon": "fa-bar-chart",
        },
        {
            "title": "Annual Usage Report",
            "type": "annual",
            "period": today.strftime("%Y"),
            "icon": "fa-line-chart",
        },
    ]

    for report in report_defs:
        if report["type"] == "daily":
            start_date = today
        elif report["type"] == "weekly":
            start_date = today - timedelta(days=6)
        elif report["type"] == "monthly":
            start_date = today.replace(day=1)
        else:
            start_date = today.replace(month=1, day=1)

        report_readings = Reading.objects.filter(
            reading_date__gte=start_date,
            reading_date__lte=today,
        )
        usage = report_readings.aggregate(total=Sum("usage_litres"))["total"] or 0

        report["usage"] = usage
        report["estimated_bill"] = estimated_reading_cost(report_readings)
        report["generated_by"] = request.user.username

    context["report_rows"] = report_defs
    start = request.GET.get('start')
    end = request.GET.get('end')
    meter_code = request.GET.get('meter')
    custom_readings = Reading.objects.select_related('meter', 'meter__user', 'meter__tariff')
    if start:
        custom_readings = custom_readings.filter(reading_date__gte=start)
    if end:
        custom_readings = custom_readings.filter(reading_date__lte=end)
    if meter_code:
        custom_readings = custom_readings.filter(meter__meter_code=meter_code)
    context['custom_rows'] = custom_readings.order_by('-created_at')[:100]
    context['meters'] = Meter.objects.order_by('meter_code')
    context['report_filters'] = {'start': start or '', 'end': end or '', 'meter': meter_code or ''}
    context['page_title'] = 'Reports'
    return render(request, 'dashboard/reports.html', context)


# =====================================================
# METER MANAGEMENT
# =====================================================
@login_required(login_url='login')
@permission_required('meters_view')
def meters(request):
    if request.method == 'POST':
        if not user_has_permission(request.user, 'meters_manage'):
            messages.error(request, "Your role can view meters but cannot register them.")
            return redirect('meters')
        form = MeterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Meter registered successfully.")
            return redirect('meters')
    else:
        form = MeterForm()

    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    meter_list = Meter.objects.select_related('user').all().order_by('id')
    if query:
        meter_list = meter_list.filter(
            Q(meter_code__icontains=query) |
            Q(location__icontains=query) |
            Q(user__full_name__icontains=query)
        )
    if status_filter:
        if status_filter == 'Offline':
            cutoff = now() - timedelta(hours=OFFLINE_AFTER_HOURS)
            meter_list = meter_list.filter(
                Q(last_seen__lt=cutoff) | Q(last_seen__isnull=True, date_assigned__lt=cutoff)
            )
        else:
            meter_list = meter_list.filter(status=status_filter)
    paginator = Paginator(meter_list, 5)

    page_number = request.GET.get('page')
    meter_rows = paginator.get_page(page_number)

    return render(request, 'dashboard/meters.html', {
        'form': form,
        'meter_rows': meter_rows,
        'page_title': 'Meters',
        'query': query,
        'status_filter': status_filter,
    })


@login_required(login_url='login')
@permission_required('meters_view')
def meter_detail(request, meter_id):
    meter = get_object_or_404(Meter.objects.select_related('tariff'), id=meter_id)
    if request.method == 'POST':
        if request.POST.get('action') == 'tariff':
            if not user_has_permission(request.user, 'meters_manage'):
                messages.error(request, "Your role cannot change meter tariffs.")
                return redirect('meter_detail', meter_id=meter.id)
            tariff = get_object_or_404(
                Tariff,
                id=request.POST.get('tariff_id'),
                active=True,
            )
            meter.tariff = tariff
            meter.save(update_fields=['tariff'])
            record_audit(
                request, 'Changed meter tariff', meter,
                f"{meter.meter_code} assigned to {tariff.name}"
            )
            messages.success(request, f"Tariff changed to {tariff.name}.")
            return redirect('meter_detail', meter_id=meter.id)

        desired_state = request.POST.get('valve_open') == 'true'
        if meter.valve_open != desired_state:
            meter.valve_open = desired_state
            meter.save(update_fields=['valve_open'])
            activity = ValveActivity.objects.create(
                meter=meter, valve_open=desired_state, source='Web', changed_by=request.user
            )
            record_audit(
                request, 'Changed valve', activity,
                f"{meter.meter_code} valve {'opened' if desired_state else 'closed'}"
            )
        messages.success(request, "Valve state updated.")
        return redirect('meter_detail', meter_id=meter.id)

    today = now().date()
    daily_usage = (
        Reading.objects.filter(meter=meter)
        .values('reading_date')
        .annotate(total=Sum('usage_litres'))
        .order_by('-reading_date')[:30]
    )
    total_billed = Bill.objects.filter(meter_code=meter.meter_code).aggregate(total=Sum('amount'))['total'] or 0
    total_paid = Payment.objects.filter(bill__meter_code=meter.meter_code).aggregate(total=Sum('amount_paid'))['total'] or 0
    return render(request, 'dashboard/meter_detail.html', {
        'meter': meter,
        'daily_usage': daily_usage,
        'today_usage': Reading.objects.filter(meter=meter, reading_date=today).aggregate(total=Sum('usage_litres'))['total'] or 0,
        'month_usage': Reading.objects.filter(meter=meter, reading_date__year=today.year, reading_date__month=today.month).aggregate(total=Sum('usage_litres'))['total'] or 0,
        'total_billed': total_billed,
        'total_paid': total_paid,
        'valve_history': meter.valve_activities.select_related('changed_by')[:20],
        'meter_alerts': Alert.objects.filter(meter=meter).order_by('-created_at')[:10],
        'tariffs': Tariff.objects.filter(active=True).order_by('name'),
        'page_title': 'Meter Analytics'
    })


def meter_qr_scan(request, meter_code):
    meter = get_object_or_404(
        Meter.objects.select_related('user'),
        meter_code=meter_code,
    )
    return render(request, 'dashboard/meter_qr_scan.html', {
        'meter': meter,
        'page_title': f'Meter {meter.meter_code}',
    })


# =====================================================
# WATER USERS
# =====================================================
@login_required(login_url='login')
@permission_required('customers_manage')
def add_water_user(request):
    if request.method == "POST":
        form = WaterUserForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Water user added successfully.")
            return redirect('meters')
    else:
        form = WaterUserForm()

    return render(request, 'dashboard/add_water_user.html', {
        'form': form,
        'page_title': 'Add Water User'
    })


@login_required(login_url='login')
@permission_required('customers_manage')
def edit_water_user(request, user_id):
    water_user = get_object_or_404(WaterUser, id=user_id)

    if request.method == "POST":
        form = WaterUserForm(request.POST, instance=water_user)
        if form.is_valid():
            form.save()
            messages.success(request, "User details updated successfully.")
            return redirect('assigned_meter_users')
    else:
        form = WaterUserForm(instance=water_user)

    return render(request, 'dashboard/add_water_user.html', {
        'form': form,
        'page_title': 'Edit Water User',
        'form_title': 'Edit Water User',
        'submit_label': 'Update User',
    })


@login_required(login_url='login')
@permission_required('customers_view')
def assigned_meter_users(request):
    users = WaterUser.objects.annotate(
        meter_count=Count('meter')
    ).filter(
        meter_count__gt=0
    ).order_by('full_name')
    query = request.GET.get('q', '').strip()
    if query:
        users = users.filter(
            Q(full_name__icontains=query) |
            Q(phone_number__icontains=query) |
            Q(nin__icontains=query) |
            Q(meter__meter_code__icontains=query)
        ).distinct()

    return render(request, 'dashboard/assigned_meter_users.html', {
        'users': users,
        'query': query,
        'page_title': 'Assigned Meter Users'
    })


@login_required(login_url='login')
@permission_required('customers_view')
def customer_detail(request, user_id):
    customer = get_object_or_404(WaterUser, id=user_id)
    meters = customer.meter_set.all()
    payments = Payment.objects.filter(bill__meter_code__in=meters.values_list('meter_code', flat=True)).order_by('-paid_at')
    bills = Bill.objects.filter(meter_code__in=meters.values_list('meter_code', flat=True)).order_by('-created_at')
    return render(request, 'dashboard/customer_detail.html', {
        'customer': customer,
        'meters': meters,
        'payments': payments[:20],
        'bills': bills[:20],
        'tickets': SupportRequest.objects.filter(Q(water_user=customer) | Q(phone_number=customer.phone_number)),
        'notifications': customer.notifications.all()[:20],
        'page_title': 'Customer Account',
    })


@login_required(login_url='login')
@permission_required('meters_manage')
def add_meter_for_user(request, user_id):
    user = get_object_or_404(WaterUser, id=user_id)

    if request.method == 'POST':
        form = ExtraMeterForm(request.POST)
        if form.is_valid():
            meter = form.save(commit=False)
            meter.user = user
            meter.save()
            messages.success(request, "Meter assigned successfully.")
            return redirect('assigned_meter_users')
    else:
        form = ExtraMeterForm()

    return render(request, 'dashboard/add_meter_for_user.html', {
        'form': form,
        'user': user,
        'page_title': 'Add Meter'
    })


# =====================================================
# METER REPLACEMENT
# =====================================================
@login_required(login_url='login')
@permission_required('replacements')
def replace_meter(request):
    if request.method == 'POST':
        form = MeterReplacementForm(request.POST)

        if form.is_valid():
            replacement = form.save(commit=False)
            old_meter = replacement.old_meter

            new_meter = Meter.objects.create(
                user=old_meter.user,
                tariff=old_meter.tariff,
                location=old_meter.location,
                status='Active'
            )

            replacement.new_meter = new_meter

            staff_id = form.cleaned_data.get('staff_id')
            try:
                staff = StaffMember.objects.get(staff_id=staff_id)
                replacement.replaced_by = staff
            except StaffMember.DoesNotExist:
                messages.error(request, "Invalid Staff ID")
                new_meter.delete()
                return redirect('replace_meter')

            replacement.save()

            old_meter.status = 'Offline'
            old_meter.save()

            messages.success(request, "Meter replaced successfully.")
            return redirect('replaced_meters')

    else:
        form = MeterReplacementForm()

    return render(request, 'dashboard/replace_meter.html', {
        'form': form,
        'page_title': 'Replace Meter'
    })


@login_required(login_url='login')
@permission_required('replacements')
def replaced_meters(request):
    replacements = MeterReplacement.objects.all().order_by('-replacement_date')

    return render(request, 'dashboard/replaced_meters.html', {
        'replacement_rows': replacements,
        'page_title': 'Replaced Meters'
    })


# =====================================================
# STAFF
# =====================================================
@login_required(login_url='login')
@permission_required('staff')
def add_staff(request):
    if request.method == 'POST':
        form = StaffForm(request.POST)
        if form.is_valid():
            staff = form.save()
            messages.success(request, f"Staff added. ID: {staff.staff_id}")
            return redirect('add_staff')
    else:
        form = StaffForm()

    return render(request, 'dashboard/add_staff.html', {
        'form': form,
        'page_title': 'Add Staff'
    })


@login_required(login_url='login')
@permission_required('staff')
def staff_members(request):
    staff_rows = StaffMember.objects.all().order_by('id')

    return render(request, 'dashboard/staff_members.html', {
        'staff_rows': staff_rows,
        'page_title': 'Staff Members'
    })


# =====================================================
# PAYMENTS
# =====================================================
@login_required(login_url='login')
@permission_required('revenue')
def revenue_payments(request):
    payments = Payment.objects.select_related('bill').order_by('-paid_at')
    query = request.GET.get('q', '').strip()
    method = request.GET.get('method', '')
    start = request.GET.get('start')
    end = request.GET.get('end')
    if query:
        payments = payments.filter(
            Q(bill__meter_code__icontains=query) |
            Q(transaction_id__icontains=query) |
            Q(phone_number__icontains=query)
        )
    if method:
        payments = payments.filter(payment_method=method)
    if start:
        payments = payments.filter(paid_at__date__gte=start)
    if end:
        payments = payments.filter(paid_at__date__lte=end)
    total_revenue = payments.aggregate(total=Sum('amount_paid'))['total'] or 0
    today = now().date()

    return render(request, 'dashboard/revenue_payments.html', {
        'payments': payments,
        'total_revenue': total_revenue,
        'today_revenue': Payment.objects.filter(paid_at__date=today).aggregate(total=Sum('amount_paid'))['total'] or 0,
        'unpaid_total': Bill.objects.exclude(status='Paid').aggregate(total=Sum('amount'))['total'] or 0,
        'paid_bills': Bill.objects.filter(status='Paid').count(),
        'unpaid_bills': Bill.objects.exclude(status='Paid').count(),
        'methods': Payment.METHOD_CHOICES,
        'filters': {'q': query, 'method': method, 'start': start or '', 'end': end or ''},
        'page_title': 'Revenue & Payments'
    })


@login_required(login_url='login')
@permission_required('offline_monitoring')
def offline_meters(request):
    cutoff = now() - timedelta(hours=OFFLINE_AFTER_HOURS)
    meters = Meter.objects.select_related('user').filter(
        Q(last_seen__lt=cutoff) | Q(last_seen__isnull=True, date_assigned__lt=cutoff)
    ).order_by('last_seen')
    return render(request, 'dashboard/offline_meters.html', {
        'meters': meters,
        'offline_hours': OFFLINE_AFTER_HOURS,
        'page_title': 'Offline Meter Monitoring',
    })


@login_required(login_url='login')
@permission_required('support')
def support_tickets(request):
    tickets = SupportRequest.objects.select_related('water_user', 'meter', 'assigned_to').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    return render(request, 'dashboard/support_tickets.html', {
        'tickets': tickets, 'status_filter': status_filter, 'page_title': 'Support Tickets'
    })


@login_required(login_url='login')
@permission_required('support_manage')
def support_ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportRequest, id=ticket_id)
    if request.method == 'POST':
        previous_status = ticket.status
        form = SupportWorkflowForm(request.POST, instance=ticket)
        if form.is_valid():
            ticket = form.save(commit=False)
            handled = ticket.status in ('Resolved', 'Closed')
            newly_handled = previous_status not in ('Resolved', 'Closed')

            if handled and newly_handled and ticket.water_user:
                resolution = ticket.resolution_notes.strip()
                Notification.objects.create(
                    water_user=ticket.water_user,
                    channel='In App',
                    subject=f"Support ticket #{ticket.id} {ticket.status.lower()}",
                    message=resolution or (
                        f"Your {ticket.issue_type.lower()} request has been "
                        f"{ticket.status.lower()}."
                    ),
                    status='Sent',
                    created_by=request.user,
                    sent_at=now(),
                )
                ticket.customer_notified_at = now()
            elif not handled:
                ticket.customer_notified_at = None

            ticket.save()
            record_audit(request, 'Updated ticket', ticket, f"Ticket marked {ticket.status}")
            if handled and newly_handled and ticket.water_user:
                messages.success(request, "Support ticket updated and the customer was notified.")
            else:
                messages.success(request, "Support ticket updated.")
            return redirect('support_tickets')
    else:
        form = SupportWorkflowForm(instance=ticket)
    return render(request, 'dashboard/workflow_form.html', {
        'form': form, 'record': ticket, 'page_title': 'Support Ticket',
        'heading': f'Ticket #{ticket.id}: {ticket.issue_type}', 'back_url': 'support_tickets',
    })


@login_required(login_url='login')
@permission_required('tariffs')
def tariffs(request):
    if request.method == 'POST':
        existing = Tariff.objects.filter(name=request.POST.get('name')).first()
        form = TariffForm(request.POST, instance=existing)
        if form.is_valid():
            tariff = form.save()
            record_audit(request, 'Saved tariff', tariff, str(tariff))
            messages.success(request, "Tariff saved.")
            return redirect('tariffs')
    else:
        form = TariffForm(initial={'effective_from': now().date(), 'active': True})
    return render(request, 'dashboard/tariffs.html', {
        'form': form, 'tariffs': Tariff.objects.all(), 'page_title': 'Tariff Management'
    })


@login_required(login_url='login')
@permission_required('notifications')
def notifications(request):
    if request.method == 'POST':
        form = NotificationForm(request.POST)
        if form.is_valid():
            notification = form.save(commit=False)
            notification.created_by = request.user
            notification.status = 'Sent' if notification.channel == 'In App' else 'Queued'
            notification.sent_at = now() if notification.channel == 'In App' else None
            notification.save()
            record_audit(request, 'Sent notification', notification, notification.subject)
            messages.success(
                request,
                "Notification sent." if notification.channel == 'In App'
                else "Notification queued for the external delivery provider."
            )
            return redirect('notifications')
    else:
        form = NotificationForm()
    return render(request, 'dashboard/notifications.html', {
        'form': form, 'notifications': Notification.objects.select_related('water_user', 'created_by'),
        'page_title': 'Customer Notifications',
    })


@login_required(login_url='login')
@permission_required('audit')
def audit_logs(request):
    logs = AuditLog.objects.select_related('actor')
    query = request.GET.get('q', '').strip()
    if query:
        logs = logs.filter(
            Q(action__icontains=query) | Q(description__icontains=query) |
            Q(actor__username__icontains=query)
        )
    return render(request, 'dashboard/audit_logs.html', {
        'logs': logs[:250], 'query': query, 'page_title': 'Audit Trail'
    })


@login_required(login_url='login')
def access_control(request):
    if not request.user.is_superuser:
        messages.error(request, "Administrator access is required.")
        return redirect('home')
    users = User.objects.all().order_by('username')
    for user in users:
        UserProfile.objects.get_or_create(user=user)
    if request.method == 'POST':
        target = get_object_or_404(User, id=request.POST.get('user_id'))
        profile = target.dashboard_profile
        form = UserRoleForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            record_audit(request, 'Changed role', target, f"{target.username} role set to {profile.role}")
            messages.success(request, "User role updated.")
            return redirect('access_control')
    return render(request, 'dashboard/access_control.html', {
        'users': users, 'roles': UserProfile.ROLE_CHOICES, 'page_title': 'Roles & Access'
    })


@login_required(login_url='login')
@permission_required('dashboard')
def profile_photo(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfilePhotoForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save()
            record_audit(request, 'Updated profile photo', profile, 'Profile photo changed')
            messages.success(request, "Profile photo updated.")
            return redirect('profile_photo')
    else:
        form = ProfilePhotoForm(instance=profile)

    return render(request, 'dashboard/profile_photo.html', {
        'form': form,
        'profile': profile,
        'page_title': 'Profile Photo',
    })


# =====================================================
# AUTH
# =====================================================
def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect('signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username exists")
            return redirect('signup')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email exists")
            return redirect('signup')

        User.objects.create_user(username=username, email=email, password=password)
        messages.success(request, "Account created")
        return redirect('login')

    return render(request, 'dashboard/signup.html')


def login_view(request):
    if request.method == 'POST':
        user = authenticate(
            username=request.POST.get('username'),
            password=request.POST.get('password')
        )

        if user:
            login(request, user)
            return redirect('home')

        messages.error(request, "Invalid login")
        return redirect('login')

    return render(request, 'dashboard/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def forgot_account_view(request):
    return render(request, 'dashboard/forgot_account.html')
