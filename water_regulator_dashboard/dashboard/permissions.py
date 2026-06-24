from django.core.exceptions import ObjectDoesNotExist


ROLE_PERMISSIONS = {
    'Administrator': {'*'},
    'Regulator': {
        'dashboard',
        'meters_view',
        'meters_manage',
        'customers_view',
        'customers_manage',
        'readings',
        'alerts',
        'alerts_manage',
        'reports',
        'offline_monitoring',
        'support',
        'support_manage',
        'notifications',
        'staff',
        'replacements',
        'audit',
    },
    'Technician': {
        'dashboard',
        'meters_view',
        'readings',
        'alerts',
        'alerts_manage',
        'offline_monitoring',
        'replacements',
    },
    'Finance': {
        'dashboard',
        'reports',
        'revenue',
        'tariffs',
    },
    'Support': {
        'dashboard',
        'customers_view',
        'support',
        'support_manage',
        'notifications',
    },
    'Viewer': {
        'dashboard',
        'readings',
        'reports',
    },
}


def permissions_for_user(user):
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {'*'}

    try:
        profile = user.dashboard_profile
    except ObjectDoesNotExist:
        profile = None
    role = profile.role if profile else 'Viewer'
    return ROLE_PERMISSIONS.get(role, set())


def user_has_permission(user, permission):
    permissions = permissions_for_user(user)
    return '*' in permissions or permission in permissions


def role_access(request):
    permissions = permissions_for_user(request.user)
    try:
        profile = request.user.dashboard_profile if request.user.is_authenticated else None
    except ObjectDoesNotExist:
        profile = None
    return {
        'role_permissions': permissions,
        'current_role': 'Administrator' if request.user.is_superuser else (
            profile.role if profile else 'Viewer'
        ),
    }
