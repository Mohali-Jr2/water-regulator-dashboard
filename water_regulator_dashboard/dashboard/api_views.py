from django.utils import timezone
from django.db.models import Sum
from django.db import transaction
from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import csv
import uuid
import random

from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from rest_framework import status

from .models import (
    WaterUser,
    Meter,
    Bill,
    Payment,
    WaterCredit,
    Reading,
    SupportRequest,
    Tariff,
    Notification,
    ValveActivity,
    MobileMoneyTransaction,
)
from .mtn_momo import (
    MomoApiError,
    MomoConfigurationError,
    request_to_pay,
    request_to_pay_status,
)

# =========================
# HELPERS
# =========================
def get_meter(meter_code):
    try:
        return Meter.objects.get(meter_code=meter_code)
    except Meter.DoesNotExist:
        return None


API_KEY = "MY_SECRET_123"


def current_rate(meter=None):
    if (
        meter
        and meter.tariff
        and meter.tariff.active
    ):
        return float(meter.tariff.rate_per_litre)
    return 5.0


def billable_readings(meter):
    readings = Reading.objects.filter(meter=meter)
    if meter.billing_started_at:
        readings = readings.filter(created_at__gte=meter.billing_started_at)
    return readings


def complete_mobile_money_transaction(momo_transaction):
    with transaction.atomic():
        momo_transaction = (
            MobileMoneyTransaction.objects
            .select_for_update()
            .select_related('bill', 'meter', 'meter__user')
            .get(id=momo_transaction.id)
        )
        if momo_transaction.payment_id:
            return momo_transaction

        meter = momo_transaction.meter
        bill = momo_transaction.bill
        payment = Payment.objects.create(
            bill=bill,
            amount_paid=float(momo_transaction.amount),
            phone_number=momo_transaction.phone_number,
            payment_method='MTN Mobile Money',
            transaction_id=str(momo_transaction.reference_id),
            payment_status='Successful',
        )

        rate = current_rate(meter)
        litres = float(momo_transaction.amount) / rate
        credit, _ = WaterCredit.objects.select_for_update().get_or_create(
            meter=meter,
            defaults={'available_litres': 0},
        )
        credit.available_litres += litres
        credit.save(update_fields=['available_litres', 'updated_at'])

        paid_total = bill.payments.aggregate(total=Sum('amount_paid'))['total'] or 0
        if float(paid_total) >= float(bill.amount):
            bill.status = 'Paid'
            bill.save(update_fields=['status'])

        momo_transaction.payment = payment
        momo_transaction.status = 'SUCCESSFUL'
        momo_transaction.save(update_fields=['payment', 'status', 'updated_at'])

        Notification.objects.create(
            water_user=meter.user,
            channel='In App',
            subject='MTN Mobile Money payment received',
            message=(
                f"Payment of UGX {float(momo_transaction.amount):.0f} was confirmed. "
                f"Transaction: {momo_transaction.reference_id}."
            ),
            status='Sent',
            sent_at=timezone.now(),
        )
        return momo_transaction

def is_authorized(request):
    return request.headers.get("X-API-KEY") == API_KEY


# =========================
# METER LATEST READING
# =========================
@api_view(['GET'])
def latest_meter_reading(request):
    meter_code = request.GET.get("meter_code") or "MTR-0001"
    meter = get_meter(meter_code)

    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    today = timezone.localdate()
    today_usage = Reading.objects.filter(
        meter=meter,
        reading_date=today
    ).aggregate(total=Sum("usage_litres"))["total"] or 0

    return Response({
        "meter_code": meter.meter_code,
        "location": meter.location,
        "status": meter.effective_status,
        "offline_after_hours": 24,
        "flow_rate": meter.current_flow_rate,
        "total_usage": meter.total_usage_litres,
        "today_usage": float(today_usage),
        "valve_open": meter.valve_open,
        "last_seen": meter.last_seen,
    })


# =========================
# USAGE INSIGHTS (REAL)
# =========================



@api_view(["GET"])
def usage_insights(request):

    today = timezone.localdate()
    meter_code = request.GET.get("meter_code")
    readings = Reading.objects.all()

    if meter_code:
        readings = readings.filter(meter__meter_code=meter_code)

    today_usage = readings.filter(
        reading_date=today
    ).aggregate(
        total=Sum("usage_litres")
    )["total"] or 0

    weekly_usage = readings.filter(
        reading_date__gte=today - timedelta(days=7)
    ).aggregate(
        total=Sum("usage_litres")
    )["total"] or 0

    return Response({
        "percentage_message":
            f"Today's usage is {today_usage:.3f} litres",

        "leakage_message":
            "No leakage detected",

        "prediction_message":
            f"Estimated weekly usage: {weekly_usage:.3f} litres",

        "today_usage": today_usage,
        "weekly_usage": weekly_usage
    })


@api_view(["GET"])
def daily_meter_usage(request):

    meter_code = request.GET.get("meter_code") or "MTR-0001"
    meter = get_meter(meter_code)

    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    today = timezone.localdate()
    today_usage = Reading.objects.filter(
        meter=meter,
        reading_date=today
    ).aggregate(
        total=Sum("usage_litres")
    )["total"] or 0

    return Response({
        "meter_code": meter.meter_code,
        "date": today,
        "daily_usage": float(today_usage),
        "usage_litres": float(today_usage),
        "message": f"{meter.meter_code} used {today_usage:.3f} litres today",
    })


# =========================
# ALERTS
# =========================
@api_view(['GET'])
def meter_alerts(request):

    meter_code = request.GET.get("meter_code")
    readings = Reading.objects.all()

    if meter_code:
        readings = readings.filter(meter__meter_code=meter_code)

    latest = readings.order_by("-id").first()

    if not latest:
        return Response([{
            "title": "No Data",
            "message": "No ESP32 readings yet",
            "severity": "Info"
        }])

    alerts = []

    if latest.usage_litres > 500:
        alerts.append({
            "title": "High Usage",
            "message": "Unusual consumption detected",
            "severity": "Warning"
        })

    return Response(alerts)


# =========================
# BILLING
# =========================
@api_view(['GET'])
def meter_bill(request):

    meter_code = request.GET.get("meter_code")
    meter = get_meter(meter_code)
    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    total = billable_readings(meter).aggregate(
        total=Sum("usage_litres")
    )["total"] or 0

    RATE = current_rate(meter)
    amount = float(total) * RATE

    return Response({
        "meter_code": meter_code,
        "total_usage": total,
        "rate": RATE,
        "tariff": meter.tariff.name if meter.tariff else "Default",
        "current_bill": amount,
        "currency": "UGX"
    })


# =========================
# SUPPORT
# =========================
@api_view(['POST'])
def create_support_request(request):

    issue_type = request.data.get("issue_type")
    phone_number = request.data.get("phone_number")
    description = request.data.get("description")

    if not all([issue_type, phone_number, description]):
        return Response({"error": "All fields required"}, status=400)

    meter_code = request.data.get("meter_code")
    meter = get_meter(meter_code) if meter_code else None
    water_user = meter.user if meter else WaterUser.objects.filter(phone_number=phone_number).first()

    ticket = SupportRequest.objects.create(
        issue_type=issue_type,
        phone_number=phone_number,
        description=description,
        meter=meter,
        water_user=water_user,
        priority=request.data.get("priority", "Medium"),
    )

    if water_user:
        Notification.objects.create(
            water_user=water_user,
            channel="In App",
            subject=f"Support ticket #{ticket.id} received",
            message="Your support request has been received and is awaiting review.",
            status="Sent",
            sent_at=timezone.now(),
        )

    return Response({"message": "Submitted", "id": ticket.id})


@api_view(['GET'])
def customer_notifications(request):
    meter = get_meter(request.GET.get("meter_code"))
    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    items = Notification.objects.filter(water_user=meter.user)[:50]
    return Response([
        {
            "id": item.id,
            "channel": item.channel,
            "subject": item.subject,
            "message": item.message,
            "status": item.status,
            "created_at": item.created_at,
        }
        for item in items
    ])


# =========================
# PAYMENT
# =========================
@api_view(['POST'])
def pay_bill(request):

    bill_id = request.data.get("bill_id")
    amount = request.data.get("amount")
    phone_number = request.data.get("phone_number")
    payment_method = request.data.get("payment_method")

    if not bill_id or not amount or not phone_number or not payment_method:
        return Response({"error": "Missing fields"}, status=400)

    valid_methods = {value for value, _ in Payment.METHOD_CHOICES}
    if payment_method not in valid_methods:
        return Response({
            "error": "Unsupported payment method",
            "payment_methods": sorted(valid_methods),
        }, status=400)

    if payment_method == 'MTN Mobile Money':
        return Response({
            'error': 'Use the MTN MoMo request-to-pay endpoint.',
            'endpoint': '/api/momo/mtn/request-to-pay/',
        }, status=400)

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return Response({"error": "Invalid amount"}, status=400)

    if amount <= 0:
        return Response({"error": "Amount must be greater than zero"}, status=400)

    try:
        bill = Bill.objects.get(id=bill_id)
    except Bill.DoesNotExist:
        return Response({"error": "Bill not found"}, status=404)

    meter = get_meter(bill.meter_code)

    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    payment = Payment.objects.create(
        bill=bill,
        amount_paid=amount,
        phone_number=phone_number,
        payment_method=payment_method,
        transaction_id=str(uuid.uuid4())[:12].upper(),
    )

    RATE = current_rate(meter)
    litres = float(amount) / RATE

    credit, _ = WaterCredit.objects.get_or_create(
        meter=meter,
        defaults={"available_litres": 0}
    )

    credit.available_litres += litres
    credit.save()

    if amount >= float(bill.amount):
        bill.status = "Paid"
        bill.save()

    Notification.objects.create(
        water_user=meter.user,
        channel="In App",
        subject="Payment received",
        message=f"Payment of UGX {amount:.0f} was received. Transaction: {payment.transaction_id}.",
        status="Sent",
        sent_at=timezone.now(),
    )

    return Response({
    "success": True,
    "transaction_id": payment.transaction_id,
    "litres_bought": litres,
    "bill_status": bill.status,
    "available_litres": credit.available_litres,
    "valve_open": meter.valve_open,
    "rate": RATE
    })


@api_view(['POST'])
def mtn_request_to_pay(request):
    bill_id = request.data.get('bill_id')
    phone_number = str(request.data.get('phone_number') or '').strip()
    amount_value = request.data.get('amount')

    if not bill_id or not phone_number or amount_value in (None, ''):
        return Response({'error': 'bill_id, amount and phone_number are required'}, status=400)

    try:
        amount = Decimal(str(amount_value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Response({'error': 'Invalid amount'}, status=400)
    if amount <= 0:
        return Response({'error': 'Amount must be greater than zero'}, status=400)

    bill = Bill.objects.filter(id=bill_id).first()
    if not bill:
        return Response({'error': 'Bill not found'}, status=404)
    meter = get_meter(bill.meter_code)
    if not meter:
        return Response({'error': 'Meter not found'}, status=404)

    reference_id = uuid.uuid4()
    momo_transaction = MobileMoneyTransaction.objects.create(
        bill=bill,
        meter=meter,
        reference_id=reference_id,
        external_id=f'BILL-{bill.id}-{reference_id.hex[:12]}',
        phone_number=phone_number,
        provider_phone_number=(
            settings.MTN_MOMO_TEST_MSISDN
            if settings.MTN_MOMO_TARGET_ENVIRONMENT == 'sandbox'
            else phone_number
        ),
        amount=amount,
        currency=settings.MTN_MOMO_CURRENCY,
    )

    try:
        status_code, _ = request_to_pay(momo_transaction)
    except MomoConfigurationError as exc:
        momo_transaction.status = 'FAILED'
        momo_transaction.provider_message = str(exc)
        momo_transaction.save(update_fields=['status', 'provider_message', 'updated_at'])
        return Response({
            'error': str(exc),
            'configuration_required': True,
        }, status=503)
    except MomoApiError as exc:
        momo_transaction.status = 'FAILED'
        momo_transaction.provider_message = str(exc)
        momo_transaction.save(update_fields=['status', 'provider_message', 'updated_at'])
        return Response({
            'error': str(exc),
            'provider_status': exc.status_code,
        }, status=502)

    if status_code != 202:
        momo_transaction.status = 'FAILED'
        momo_transaction.provider_message = f'Unexpected MTN response: {status_code}'
        momo_transaction.save(update_fields=['status', 'provider_message', 'updated_at'])
        return Response({'error': momo_transaction.provider_message}, status=502)

    return Response({
        'success': True,
        'reference_id': str(reference_id),
        'status': 'PENDING',
        'message': 'Payment request accepted. Approve it in the MTN MoMo prompt.',
        'sandbox': settings.MTN_MOMO_TARGET_ENVIRONMENT == 'sandbox',
        'sandbox_msisdn': momo_transaction.provider_phone_number,
        'currency': momo_transaction.currency,
    }, status=202)


@api_view(['GET'])
def mtn_payment_status(request, reference_id):
    momo_transaction = (
        MobileMoneyTransaction.objects
        .select_related('bill', 'meter')
        .filter(reference_id=reference_id)
        .first()
    )
    if not momo_transaction:
        return Response({'error': 'Transaction not found'}, status=404)

    if momo_transaction.status == 'PENDING':
        try:
            payload = request_to_pay_status(reference_id)
        except MomoConfigurationError as exc:
            return Response({'error': str(exc), 'configuration_required': True}, status=503)
        except MomoApiError as exc:
            return Response({
                'error': str(exc),
                'provider_status': exc.status_code,
            }, status=502)

        provider_status = str(payload.get('status') or 'PENDING').upper()
        momo_transaction.provider_message = (
            payload.get('reason')
            or payload.get('financialTransactionId')
            or ''
        )
        if provider_status in ('SUCCESSFUL', 'FAILED'):
            momo_transaction.status = provider_status
        momo_transaction.save(
            update_fields=['status', 'provider_message', 'updated_at']
        )
        if provider_status == 'SUCCESSFUL':
            momo_transaction = complete_mobile_money_transaction(momo_transaction)

    response = {
        'reference_id': str(momo_transaction.reference_id),
        'status': momo_transaction.status,
        'message': momo_transaction.provider_message,
    }
    if momo_transaction.payment_id:
        credit = WaterCredit.objects.filter(meter=momo_transaction.meter).first()
        response.update({
            'success': True,
            'transaction_id': momo_transaction.payment.transaction_id,
            'litres_bought': float(momo_transaction.amount) / current_rate(momo_transaction.meter),
            'available_litres': credit.available_litres if credit else 0,
            'bill_status': momo_transaction.bill.status,
            'valve_open': momo_transaction.meter.valve_open,
            'rate': current_rate(momo_transaction.meter),
        })
    return Response(response)

# =========================
# ESP32 UPDATE (REAL TIME)
# =========================
@api_view(['POST'])
def esp32_update(request):

    if not is_authorized(request):
        return Response({"error": "Unauthorized"}, status=401)

    meter_code = request.data.get("meter_code")
    flow_rate = request.data.get("flow_rate")
    total_litres = request.data.get("litres")

    if not meter_code or flow_rate is None or total_litres is None:
        return Response({"error": "Missing fields"}, status=400)

    try:
        flow_rate = float(flow_rate)
        total_litres = float(total_litres)
    except ValueError:
        return Response({"error": "Invalid values"}, status=400)

    meter = get_meter(meter_code)

    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    previous_total = meter.total_usage_litres

    usage_since_last_update = total_litres - previous_total

    if usage_since_last_update < 0:
        usage_since_last_update = 0

    meter.current_flow_rate = flow_rate
    meter.total_usage_litres = total_litres
    meter.last_seen = timezone.now()
    meter.save()

    if usage_since_last_update > 0:
        Reading.objects.create(
            meter=meter,
            usage_litres=usage_since_last_update,
            flow_rate=flow_rate
        )

    result = recalculate_meter_billing(meter)

     # REAL TIME BILLING ENGINE TRIGGER

    return Response({
        "success": True,
        "meter_code": meter.meter_code,
        "flow_rate": flow_rate,
        "total_litres": total_litres,
        "used_this_update": usage_since_last_update,
        "valve_open": result["valve_open"],
        "remaining_value": result["remaining_value"]
    })

   
# =========================
# VALVE CONTROL
# =========================
@api_view(['POST'])
def control_valve(request):

    meter = get_meter(request.data.get("meter_code"))
    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    meter.valve_open = request.data.get("valve_open")

    # if manually closed → override system
    meter.save()

    return Response({
        "message": "Valve updated",
        "valve_open": meter.valve_open
    })


# =========================
# VALVE STATUS
# =========================
@api_view(['GET'])
def get_valve_status(request):

    meter = Meter.objects.filter(meter_code="MTR-0001").first()

    return Response({
        "meter_code": meter.meter_code,
        "valve_open": meter.valve_open
    })


# =========================
# MOBILE REGISTER
# =========================






@api_view(['POST'])
def mobile_register(request):

    data = request.data or {}

    phone_number = data.get("phoneNumber") or data.get("phone_number")
    meter_code = data.get("meterCode") or data.get("meter_code")
    email = data.get("email")
    password = data.get("password")

    # ======================
    # VALIDATION
    # ======================
    if not phone_number:
        return Response({"error": "phoneNumber is required"}, status=400)

    if not password:
        return Response({"error": "password is required"}, status=400)

    if not meter_code:
        return Response({"error": "meterCode is required"}, status=400)

    # ======================
    # CHECK METER EXISTS
    # ======================
    try:
        meter = Meter.objects.get(meter_code=meter_code)
    except Meter.DoesNotExist:
        return Response({"error": "Invalid meter code"}, status=404)

    user = meter.user

    # ======================
    # CHECK IF ALREADY REGISTERED (THIS METER)
    # ======================
    if user.mobile_account_created:
        return Response({
            "error": "This meter is already registered"
        }, status=400)

    # ======================
    # CHECK PHONE DUPLICATE
    # ======================
    if WaterUser.objects.filter(phone_number=phone_number).exclude(id=user.id).exists():
        return Response({
            "error": "Phone number already registered"
        }, status=400)

    # ======================
    # CHECK EMAIL DUPLICATE (if provided)
    # ======================
    if email:
        if WaterUser.objects.filter(email=email).exclude(id=user.id).exists():
            return Response({
                "error": "Email already registered"
            }, status=400)

    # ======================
    # REGISTER USER
    # ======================
    user.phone_number = phone_number
    user.email = email
    user.mobile_password = make_password(password)
    user.mobile_account_created = True
    user.save()

    return Response({
        "success": True,
        "message": "Registration successful",
        "user_id": user.id,
        "meter_code": meter.meter_code
    })


# =========================
# MOBILE LOGIN
# =========================
@api_view(['POST'])
def mobile_login(request):

    phone_number = request.data.get("phone_number")
    meter_code = request.data.get("meter_code")
    password = request.data.get("password")

    try:
        # STEP 1: get meter using meter_code
        meter = Meter.objects.get(meter_code=meter_code)

        # STEP 2: get user linked to that meter
        user = meter.user

        # STEP 3: confirm phone matches (extra security)
        if user.phone_number != phone_number:
            return Response(
                {"error": "Phone number does not match this meter"},
                status=401
            )

    except Meter.DoesNotExist:
        return Response(
            {"error": "Invalid meter code"},
            status=401
        )

    # password check
    if not user.mobile_password:
        return Response(
            {"error": "Mobile account not set. Please register first."},
            status=400
        )

    if not check_password(password, user.mobile_password):
        return Response(
            {"error": "Invalid credentials"},
            status=401
        )

    return Response({
        "success": True,
        "full_name": user.full_name,
        "meter_code": meter.meter_code,
        "location": meter.location
    })

# =========================
# RESET CODE
# =========================
@api_view(['POST'])
def send_reset_code(request):

    email = request.data.get("email")

    user = WaterUser.objects.get(email=email)

    code = str(random.randint(100000, 999999))
    user.reset_code = code
    user.save()

    send_mail(
        "Reset Code",
        code,
        None,
        [email],
        fail_silently=True
    )

    return Response({"message": "Sent"})


# =========================
# RESET PASSWORD
# =========================
@api_view(['POST'])
def reset_password(request):

    user = WaterUser.objects.get(
        email=request.data.get("email"),
        reset_code=request.data.get("code")
    )

    user.mobile_password = make_password(request.data.get("new_password"))
    user.reset_code = ""
    user.save()

    return Response({"message": "Password updated"})


# =========================
# CURRENT BILL
# =========================
@api_view(['GET'])
def current_bill(request):

    meter_code = request.GET.get("meter_code") or "MTR-0001"
    meter = get_meter(meter_code)

    if not meter:
        return Response({"error": "Meter not found"}, status=404)

    total_usage = billable_readings(meter).aggregate(
        total=Sum("usage_litres")
    )["total"] or 0

    RATE = current_rate(meter)
    amount = float(total_usage) * RATE
    today = timezone.localdate()
    billing_period = today.strftime("%Y-%m")
    due_date = today + timedelta(days=30)

    bill = (
        Bill.objects
        .filter(meter_code=meter.meter_code, billing_period=billing_period)
        .order_by("-id")
        .first()
    )

    if bill is None:
        bill = Bill.objects.create(
            meter_code=meter.meter_code,
            billing_period=billing_period,
            usage_litres=float(total_usage),
            amount=amount,
            due_date=due_date,
        )
    elif bill.status != "Paid":
        bill.usage_litres = float(total_usage)
        bill.amount = amount
        bill.due_date = due_date
        bill.save()

    return Response({
        "id": bill.id,
        "meter_code": meter.meter_code,
        "billing_period": bill.billing_period,
        "usage_litres": bill.usage_litres,
        "amount": bill.amount,
        "status": bill.status,
        "due_date": bill.due_date,
        "total_usage": total_usage,
        "rate": RATE,
        "tariff": meter.tariff.name if meter.tariff else "Default",
        "current_bill": bill.amount,
        "currency": "UGX",
        "valve_open": meter.valve_open
    })


# =========================
# PAYMENT HISTORY
# =========================
@api_view(['GET'])
def payment_history(request):

    meter_code = request.GET.get("meter_code")

    payments = Payment.objects.filter(
        bill__meter_code=meter_code
    ).order_by("-paid_at")

    return Response([
        {
            "title": f"{p.payment_method} payment",
            "amount": p.amount_paid,
            "status": p.payment_status,
            "date": p.paid_at,
            "transaction_id": p.transaction_id,
            "payment_method": p.payment_method,
            "payment_status": p.payment_status,
            "paid_at": p.paid_at,
        }
        for p in payments
    ])


# =========================
# WATER CREDIT
# =========================
@api_view(['GET'])
def water_credit_balance(request, meter_code):

    credit = WaterCredit.objects.filter(meter__meter_code=meter_code).first()

    return Response({
    "meter_code": meter_code,
    "available_litres": credit.available_litres if credit else 0
})


# =========================
# REPORTS
# =========================
REPORT_TITLES = {
    "daily": "Daily Usage Report",
    "weekly": "Weekly Usage Report",
    "monthly": "Monthly Usage Report",
    "annual": "Annual Usage Report",
}


def report_date_range(report_type):
    today = timezone.localdate()

    if report_type == "daily":
        return today, today

    if report_type == "weekly":
        return today - timedelta(days=6), today

    if report_type == "monthly":
        return today.replace(day=1), today

    if report_type == "annual":
        return today.replace(month=1, day=1), today

    return None, None


def report_rows(report_type):
    start_date, end_date = report_date_range(report_type)

    if start_date is None:
        return None

    readings = (
        Reading.objects
        .select_related("meter", "meter__user")
        .filter(reading_date__gte=start_date, reading_date__lte=end_date)
        .order_by("reading_date", "meter__meter_code")
    )

    grouped = (
        readings
        .values(
            "reading_date",
            "meter__meter_code",
            "meter__location",
            "meter__user__full_name",
            "meter__tariff__name",
            "meter__tariff__rate_per_litre",
            "meter__tariff__active",
            "meter__tariff__effective_from",
        )
        .annotate(total_usage=Sum("usage_litres"))
        .order_by("reading_date", "meter__meter_code")
    )

    rows = [
        {
            "date": item["reading_date"],
            "meter_code": item["meter__meter_code"],
            "owner": item["meter__user__full_name"] or "Unassigned",
            "location": item["meter__location"],
            "tariff": item["meter__tariff__name"] or "Default",
            "usage_litres": float(item["total_usage"] or 0),
            "estimated_bill": float(item["total_usage"] or 0) * (
                float(item["meter__tariff__rate_per_litre"])
                if (
                    item["meter__tariff__rate_per_litre"] is not None
                    and item["meter__tariff__active"]
                )
                else 5.0
            ),
        }
        for item in grouped
    ]

    return {
        "title": REPORT_TITLES[report_type],
        "start_date": start_date,
        "end_date": end_date,
        "rows": rows,
        "total_usage": sum(row["usage_litres"] for row in rows),
        "total_bill": sum(row["estimated_bill"] for row in rows),
    }


def pdf_escape(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def simple_pdf(title, lines):
    stream_lines = [
        "BT",
        "/F1 18 Tf",
        "50 790 Td",
        f"({pdf_escape(title)}) Tj",
        "/F1 10 Tf",
    ]

    for line in lines[:42]:
        stream_lines.append("0 -18 Td")
        stream_lines.append(f"({pdf_escape(line)}) Tj")

    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


@api_view(['GET'])
def download_pdf_report(request, report_type):
    report_type = report_type.lower()
    data = report_rows(report_type)
    generated_by = (
        request.user.username
        if request.user.is_authenticated
        else "Mobile user"
    )

    if data is None:
        return Response({"error": "Invalid report type"}, status=400)

    lines = [
        f"Period: {data['start_date']} to {data['end_date']}",
        f"Generated by: {generated_by}",
        f"Total usage: {data['total_usage']:.3f} L",
        f"Estimated bill: UGX {data['total_bill']:.0f}",
        "",
        "Date | Meter | Owner | Tariff | Location | Usage (L) | Estimated Bill",
    ]

    for row in data["rows"]:
        lines.append(
            f"{row['date']} | {row['meter_code']} | {row['owner']} | {row['tariff']} | "
            f"{row['location']} | {row['usage_litres']:.3f} | UGX {row['estimated_bill']:.0f}"
        )

    if not data["rows"]:
        lines.append("No readings found for this period.")

    response = HttpResponse(
        simple_pdf(data["title"], lines),
        content_type="application/pdf",
    )
    filename = f"{report_type}-usage-report.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
def download_excel_report(request, report_type):
    report_type = report_type.lower()
    data = report_rows(report_type)
    generated_by = (
        request.user.username
        if request.user.is_authenticated
        else "Mobile user"
    )

    if data is None:
        return Response({"error": "Invalid report type"}, status=400)

    response = HttpResponse(content_type="text/csv")
    filename = f"{report_type}-usage-report.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([data["title"]])
    writer.writerow(["Period", data["start_date"], data["end_date"]])
    writer.writerow(["Generated By", generated_by])
    writer.writerow(["Total Usage (L)", f"{data['total_usage']:.3f}"])
    writer.writerow(["Estimated Bill (UGX)", f"{data['total_bill']:.0f}"])
    writer.writerow([])
    writer.writerow(["Date", "Meter Code", "Owner", "Tariff", "Location", "Usage (L)", "Estimated Bill (UGX)"])

    for row in data["rows"]:
        writer.writerow([
            row["date"],
            row["meter_code"],
            row["owner"],
            row["tariff"],
            row["location"],
            f"{row['usage_litres']:.3f}",
            f"{row['estimated_bill']:.0f}",
        ])

    return response

RATE_PER_LITRE = 5


def recalculate_meter_billing(meter: Meter):
    """
    Central billing engine (REAL TIME)
    """

    total_usage = billable_readings(meter).aggregate(
        total=Sum("usage_litres")
    )["total"] or 0

    # GET OR CREATE CREDIT
    credit, _ = WaterCredit.objects.get_or_create(
        meter=meter,
        defaults={"available_litres": 0}
    )

    # convert credit litres to value deduction logic
    rate = current_rate(meter)
    bill_amount = float(total_usage) * rate

    # convert credit litres into value
    credit_value = credit.available_litres * rate

    remaining_value = credit_value - bill_amount

    # AUTO VALVE LOGIC
    if remaining_value <= 0:
        meter.valve_open = True
    else:
        meter.valve_open = True

    meter.save()

    return {
        "total_usage": total_usage,
        "bill_amount": bill_amount,
        "credit_litres": credit.available_litres,
        "remaining_value": remaining_value,
        "valve_open": meter.valve_open,
    }

@api_view(["GET"])
def usage_chart(request):
    meter_code = request.GET.get("meter_code")
    readings = Reading.objects.all()

    if meter_code:
        readings = readings.filter(meter__meter_code=meter_code)

    data = (
        readings
        .values("reading_date")
        .annotate(total=Sum("usage_litres"))
        .order_by("reading_date")
    )

    return Response({
        "daily": [
            {
                "label": str(item["reading_date"]),
                "usage": float(item["total"])
            }
            for item in data
        ],
        "weekly": [],
        "monthly": [],
        "annual": []
    })

# ESP32 Functions


    # Save reading
    Reading.objects.create(
        meter=meter,
        usage_litres=litres,
        flow_rate=flow_rate
    )

    # Run billing engine
    result = recalculate_meter_billing(meter)

    return Response({
        "success": True,
        "meter_code": meter.meter_code,
        "flow_rate": flow_rate,
        "litres": litres,
        "valve_open": result["valve_open"],
        "remaining_value": result["remaining_value"]
    })


# =========================
# VALVE STATUS
# =========================
@api_view(['GET'])
def get_valve_status(request):

    meter_code = request.GET.get("meter_code")

    if not meter_code:
        return Response(
            {"error": "meter_code is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    meter = get_meter(meter_code)

    if meter is None:
        return Response(
            {"error": "Meter not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response({
        "success": True,
        "meter_code": meter.meter_code,
        "valve_open": meter.valve_open,
        "last_seen": meter.last_seen,
    })


# =========================
# MANUAL VALVE CONTROL
# =========================
@api_view(['POST'])
def control_valve(request):

    meter_code = request.data.get("meter_code")
    valve_open = request.data.get("valve_open")

    if meter_code is None or valve_open is None:
        return Response(
            {"error": "meter_code and valve_open required"},
            status=400
        )

    meter = get_meter(meter_code)

    if not meter:
        return Response(
            {"error": "Meter not found"},
            status=404
        )

    if isinstance(valve_open, str):
        valve_open = valve_open.lower() in ("true", "1", "yes", "open")
    else:
        valve_open = bool(valve_open)

    meter.valve_open = valve_open
    meter.save()
    ValveActivity.objects.create(
        meter=meter,
        valve_open=valve_open,
        source="Mobile",
    )

    return Response({
        "success": True,
        "meter_code": meter.meter_code,
        "valve_open": meter.valve_open
    }) 

