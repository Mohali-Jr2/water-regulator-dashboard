from django.db import models
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils import timezone
from io import BytesIO
import qrcode
import re
from datetime import timedelta


# =========================
# WATER USER
# =========================
class WaterUser(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone_number = models.CharField(max_length=20)
    location = models.CharField(max_length=120)
    nin = models.CharField(max_length=50, unique=True)

    LAND_STATUS_CHOICES = [
        ('Ownership', 'Full Ownership'),
        ('Leased', 'Leased'),
    ]

    land_status = models.CharField(
        max_length=20,
        choices=LAND_STATUS_CHOICES,
        default='Ownership'
    )

    mobile_password = models.CharField(max_length=128, blank=True, null=True)
    reset_code = models.CharField(max_length=10, blank=True, null=True)
    mobile_account_created = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name


# =========================
# METER (REAL IoT DEVICE)
# =========================
class Meter(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Warning', 'Warning'),
        ('Offline', 'Offline'),
    ]

    meter_code = models.CharField(max_length=50, unique=True, blank=True)
    user = models.ForeignKey(WaterUser, on_delete=models.CASCADE)
    tariff = models.ForeignKey(
        'Tariff',
        on_delete=models.PROTECT,
        related_name='meters',
        null=True,
    )
    location = models.CharField(max_length=120)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')

    qr_code = models.ImageField(upload_to='meter_qrcodes/', blank=True, null=True)

    # ================= IoT FIELDS =================
    valve_open = models.BooleanField(default=True)
    current_flow_rate = models.FloatField(default=0)
    total_usage_litres = models.FloatField(default=0)
    last_seen = models.DateTimeField(null=True, blank=True)
    billing_started_at = models.DateTimeField(default=timezone.now)
    device_token = models.CharField(max_length=100, blank=True, null=True)

    date_assigned = models.DateTimeField(auto_now_add=True)

    def generate_qr_code(self):
        qr_data = f"{settings.QR_BASE_URL}/scan/meter/{self.meter_code}/"
        qr_img = qrcode.make(qr_data)
        buffer = BytesIO()
        qr_img.save(buffer, format='PNG')
        file_name = f"{self.meter_code}.png"
        self.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):

        # AUTO METER CODE
        if not self.meter_code:
            last_meter = Meter.objects.order_by('id').last()

            if last_meter and last_meter.meter_code:
                numbers = re.findall(r'\d+', last_meter.meter_code)
                last_number = int(numbers[-1]) if numbers else 0
                new_number = last_number + 1
            else:
                new_number = 1

            self.meter_code = f"MTR-{new_number:04d}"

        super().save(*args, **kwargs)

        if not self.qr_code:
            self.generate_qr_code()
            super().save(update_fields=['qr_code'])

    def __str__(self):
        return self.meter_code

    @property
    def is_offline(self):
        reference_time = self.last_seen or self.date_assigned
        return reference_time <= timezone.now() - timedelta(hours=24)

    @property
    def effective_status(self):
        return "Offline" if self.is_offline else self.status


# =========================
# REAL TIME READING (ESP32)
# =========================
class Reading(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE)

    usage_litres = models.FloatField()
    flow_rate = models.FloatField(default=0)

    reading_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.meter.meter_code} - {self.reading_date}"


# =========================
# ALERTS (AUTO GENERATED)
# =========================
# =========================
# STAFF
# =========================
class StaffMember(models.Model):
    staff_id = models.CharField(max_length=50, unique=True, blank=True)
    full_name = models.CharField(max_length=100)
    role = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.staff_id:
            last = StaffMember.objects.order_by('id').last()
            num = int(last.staff_id.split('-')[-1]) + 1 if last else 1
            self.staff_id = f"STF-{num:03d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff_id} - {self.full_name}"


# =========================
# METER REPLACEMENT
# =========================
class MeterReplacement(models.Model):
    REASON_CHOICES = [
        ('Faulty', 'Faulty'),
        ('Stolen', 'Stolen'),
        ('Damaged', 'Damaged'),
        ('Lost', 'Lost'),
        ('Upgrade', 'Upgrade'),
        ('Other', 'Other'),
    ]

    old_meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='old_replacements')
    new_meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='new_replacements')

    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    description = models.TextField(blank=True, null=True)

    replaced_by = models.ForeignKey(StaffMember, on_delete=models.SET_NULL, null=True, blank=True)

    replacement_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        staff = self.replaced_by.full_name if self.replaced_by else "Unknown"
        return f"{self.old_meter} → {self.new_meter} by {staff}"


# =========================
# SUPPORT SYSTEM
# =========================
class SupportRequest(models.Model):
    ISSUE_CHOICES = [
        ('Leakage', 'Leakage'),
        ('Faulty Meter', 'Faulty Meter'),
        ('Wrong Bill', 'Wrong Bill'),
        ('General Support', 'General Support'),
    ]

    issue_type = models.CharField(max_length=50, choices=ISSUE_CHOICES)
    phone_number = models.CharField(max_length=20)
    description = models.TextField()

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]

    water_user = models.ForeignKey(
        WaterUser, on_delete=models.SET_NULL, null=True, blank=True
    )
    meter = models.ForeignKey(
        Meter, on_delete=models.SET_NULL, null=True, blank=True
    )
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    resolution_notes = models.TextField(blank=True)
    customer_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.issue_type}"


# =========================
# BILLING
# =========================
class Bill(models.Model):
    meter_code = models.CharField(max_length=50)
    billing_period = models.CharField(max_length=50)

    usage_litres = models.FloatField()
    amount = models.FloatField()

    status = models.CharField(max_length=20, default='Unpaid')
    due_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.meter_code}"


# =========================
# PAYMENT
# =========================
class Payment(models.Model):
    METHOD_CHOICES = [
        ('MTN Mobile Money', 'MTN Mobile Money'),
        ('Airtel Money', 'Airtel Money'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cash', 'Cash'),
        ('Card', 'Card'),
    ]

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='payments')

    payment_method = models.CharField(max_length=50, choices=METHOD_CHOICES)
    phone_number = models.CharField(max_length=20)

    amount_paid = models.FloatField()
    transaction_id = models.CharField(max_length=100, unique=True)

    payment_status = models.CharField(max_length=20, default='Successful')
    paid_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.transaction_id


class MobileMoneyTransaction(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESSFUL', 'Successful'),
        ('FAILED', 'Failed'),
    ]

    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name='mobile_money_transactions',
    )
    meter = models.ForeignKey(
        Meter,
        on_delete=models.CASCADE,
        related_name='mobile_money_transactions',
    )
    provider = models.CharField(max_length=30, default='MTN MoMo')
    reference_id = models.UUIDField(unique=True)
    external_id = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20)
    provider_phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='EUR')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
    )
    provider_message = models.TextField(blank=True)
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mobile_money_transaction',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


# =========================
# WATER CREDIT (REAL LINKED)
# =========================
class WaterCredit(models.Model):
    meter = models.OneToOneField(Meter, on_delete=models.CASCADE)
    available_litres = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


# =========================
# OPERATIONS
# =========================
class Alert(models.Model):
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Acknowledged', 'Acknowledged'),
        ('Resolved', 'Resolved'),
    ]

    meter = models.ForeignKey(Meter, on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Open")
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.meter.meter_code} - {self.alert_type}"


class ValveActivity(models.Model):
    meter = models.ForeignKey(Meter, on_delete=models.CASCADE, related_name='valve_activities')
    valve_open = models.BooleanField()
    source = models.CharField(max_length=30, default='Web')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Tariff(models.Model):
    NAME_CHOICES = [
        ('Domestic', 'Domestic'),
        ('Commercial', 'Commercial'),
        ('Industrial', 'Industrial'),
    ]

    name = models.CharField(max_length=100, choices=NAME_CHOICES, unique=True)
    rate_per_litre = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_from']

    def __str__(self):
        return f"{self.name} - UGX {self.rate_per_litre}/L"


class Notification(models.Model):
    CHANNEL_CHOICES = [('SMS', 'SMS'), ('Email', 'Email'), ('In App', 'In App')]

    water_user = models.ForeignKey(WaterUser, on_delete=models.CASCADE, related_name='notifications')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='In App')
    subject = models.CharField(max_length=150)
    message = models.TextField()
    status = models.CharField(max_length=20, default='Queued')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('Administrator', 'Administrator'),
        ('Regulator', 'Regulator'),
        ('Technician', 'Technician'),
        ('Finance', 'Finance'),
        ('Support', 'Support'),
        ('Viewer', 'Viewer'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dashboard_profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='Regulator')
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"
