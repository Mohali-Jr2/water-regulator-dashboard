from django import forms
from .models import (
    Alert,
    Meter,
    Notification,
    StaffMember,
    SupportRequest,
    Tariff,
    UserProfile,
    WaterUser,
    MeterReplacement,
)


# =========================
# METER FORM (IoT READY)
# =========================
class MeterForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = WaterUser.objects.filter(
            meter__isnull=True
        ).order_by('full_name')
        self.fields['tariff'].queryset = Tariff.objects.filter(
            active=True
        ).order_by('name')

    class Meta:
        model = Meter
        fields = ['user', 'tariff', 'location', 'status', 'valve_open', 'device_token']

        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'tariff': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter meter location'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'valve_open': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'device_token': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ESP32 device token (optional)'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get("user")

        # Prevent multiple active meters per user (IoT rule)
        if user and Meter.objects.filter(user=user, status="Active").exists():
            raise forms.ValidationError(
                "This user already has an active meter."
            )

        return cleaned_data


# =========================
# WATER USER FORM
# =========================
class WaterUserForm(forms.ModelForm):

    class Meta:
        model = WaterUser
        fields = ['full_name', 'phone_number', 'location', 'nin', 'land_status']

        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full name'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter user location'
            }),
            'nin': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter NIN'
            }),
            'land_status': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

    def clean_nin(self):
        nin = self.cleaned_data.get('nin')

        if WaterUser.objects.filter(nin=nin).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("NIN already exists")

        return nin

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')

        if WaterUser.objects.filter(phone_number=phone_number).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Phone number already exists")

        return phone_number


# =========================
# EXTRA METER FORM
# =========================
class ExtraMeterForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tariff'].queryset = Tariff.objects.filter(
            active=True
        ).order_by('name')

    class Meta:
        model = Meter
        fields = ['tariff', 'location', 'status', 'valve_open']

        widgets = {
            'tariff': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter meter location'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'valve_open': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


# =========================
# METER REPLACEMENT FORM (FIXED)
# =========================
class MeterReplacementForm(forms.ModelForm):

    staff_id = forms.CharField(
        label="Staff ID",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g STF-001'
        })
    )

    class Meta:
        model = MeterReplacement
        fields = ['old_meter', 'reason', 'description', 'staff_id']

        widgets = {
            'old_meter': forms.Select(attrs={'class': 'form-control'}),
            'reason': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
        }


# =========================
# STAFF FORM
# =========================
class StaffForm(forms.ModelForm):

    class Meta:
        model = StaffMember
        fields = ['full_name', 'role', 'phone_number']

        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full name'
            }),
            'role': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g Technician'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
        }


class AlertWorkflowForm(forms.ModelForm):
    class Meta:
        model = Alert
        fields = ['status', 'assigned_to', 'notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SupportWorkflowForm(forms.ModelForm):
    class Meta:
        model = SupportRequest
        fields = ['status', 'priority', 'assigned_to', 'resolution_notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'resolution_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class TariffForm(forms.ModelForm):
    class Meta:
        model = Tariff
        fields = ['name', 'rate_per_litre', 'effective_from', 'active']
        widgets = {
            'name': forms.Select(attrs={'class': 'form-control'}),
            'rate_per_litre': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'effective_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'active': forms.CheckboxInput(),
        }


class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = ['water_user', 'channel', 'subject', 'message']
        widgets = {
            'water_user': forms.Select(attrs={'class': 'form-control'}),
            'channel': forms.Select(attrs={'class': 'form-control'}),
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['role']
        widgets = {'role': forms.Select(attrs={'class': 'form-control input-sm'})}


class ProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['photo']
        widgets = {
            'photo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/webp',
            })
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose an image smaller than 5 MB.")
        return photo
