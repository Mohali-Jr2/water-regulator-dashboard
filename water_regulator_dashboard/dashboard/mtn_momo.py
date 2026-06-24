import base64
import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache


class MomoConfigurationError(Exception):
    pass


class MomoApiError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _configuration():
    values = {
        'subscription_key': settings.MTN_MOMO_SUBSCRIPTION_KEY,
        'api_user': settings.MTN_MOMO_API_USER,
        'api_key': settings.MTN_MOMO_API_KEY,
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise MomoConfigurationError(
            'Missing MTN MoMo sandbox configuration: ' + ', '.join(missing)
        )
    return values


def _request(method, path, headers=None, body=None):
    request = urllib.request.Request(
        f'{settings.MTN_MOMO_BASE_URL}{path}',
        data=json.dumps(body).encode('utf-8') if body is not None else None,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read().decode('utf-8')
            return response.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        content = exc.read().decode('utf-8', errors='replace')
        try:
            payload = json.loads(content) if content else {}
        except json.JSONDecodeError:
            payload = {'message': content}
        raise MomoApiError(
            payload.get('message') or payload.get('code') or 'MTN MoMo request failed',
            status_code=exc.code,
            payload=payload,
        ) from exc
    except urllib.error.URLError as exc:
        raise MomoApiError(f'Could not connect to MTN MoMo: {exc.reason}') from exc


def access_token():
    cached = cache.get('mtn_momo_collection_token')
    if cached:
        return cached

    config = _configuration()
    credentials = base64.b64encode(
        f"{config['api_user']}:{config['api_key']}".encode('utf-8')
    ).decode('ascii')
    _, payload = _request(
        'POST',
        '/collection/token/',
        headers={
            'Authorization': f'Basic {credentials}',
            'Ocp-Apim-Subscription-Key': config['subscription_key'],
        },
    )
    token = payload.get('access_token')
    if not token:
        raise MomoApiError('MTN MoMo did not return an access token', payload=payload)

    expires_in = max(int(payload.get('expires_in', 3600)) - 60, 60)
    cache.set('mtn_momo_collection_token', token, expires_in)
    return token


def collection_headers(reference_id=None):
    config = _configuration()
    headers = {
        'Authorization': f'Bearer {access_token()}',
        'Ocp-Apim-Subscription-Key': config['subscription_key'],
        'X-Target-Environment': settings.MTN_MOMO_TARGET_ENVIRONMENT,
        'Content-Type': 'application/json',
    }
    if reference_id:
        headers['X-Reference-Id'] = str(reference_id)
    return headers


def request_to_pay(transaction):
    return _request(
        'POST',
        '/collection/v1_0/requesttopay',
        headers=collection_headers(transaction.reference_id),
        body={
            'amount': format(transaction.amount, '.2f'),
            'currency': transaction.currency,
            'externalId': transaction.external_id,
            'payer': {
                'partyIdType': 'MSISDN',
                'partyId': transaction.provider_phone_number,
            },
            'payerMessage': f'Water bill {transaction.bill.billing_period}',
            'payeeNote': f'Payment for meter {transaction.meter.meter_code}',
        },
    )


def request_to_pay_status(reference_id):
    _, payload = _request(
        'GET',
        f'/collection/v1_0/requesttopay/{reference_id}',
        headers=collection_headers(),
    )
    return payload
