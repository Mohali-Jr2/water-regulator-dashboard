import json
import uuid
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand, CommandError


BASE_URL = 'https://sandbox.momodeveloper.mtn.com'


class Command(BaseCommand):
    help = 'Provision an MTN MoMo sandbox API user and API key.'

    def add_arguments(self, parser):
        parser.add_argument('--subscription-key', required=True)
        parser.add_argument(
            '--callback-host',
            default='192.168.1.78',
            help='Host only, without http://, https://, port, or path.',
        )

    def handle(self, *args, **options):
        subscription_key = options['subscription_key'].strip()
        callback_host = options['callback_host'].strip()
        api_user = str(uuid.uuid4())
        common_headers = {
            'Ocp-Apim-Subscription-Key': subscription_key,
            'Content-Type': 'application/json',
        }

        self._request(
            'POST',
            '/v1_0/apiuser',
            headers={
                **common_headers,
                'X-Reference-Id': api_user,
            },
            body={'providerCallbackHost': callback_host},
            expected_status=201,
        )
        _, payload = self._request(
            'POST',
            f'/v1_0/apiuser/{api_user}/apikey',
            headers=common_headers,
            expected_status=201,
        )
        api_key = payload.get('apiKey')
        if not api_key:
            raise CommandError('MTN created the API user but did not return an API key.')

        self.stdout.write(self.style.SUCCESS('MTN sandbox credentials created.'))
        self.stdout.write('Set these before starting Django:')
        self.stdout.write(f'$env:MTN_MOMO_SUBSCRIPTION_KEY="{subscription_key}"')
        self.stdout.write(f'$env:MTN_MOMO_API_USER="{api_user}"')
        self.stdout.write(f'$env:MTN_MOMO_API_KEY="{api_key}"')

    def _request(self, method, path, headers, expected_status, body=None):
        request = urllib.request.Request(
            f'{BASE_URL}{path}',
            data=json.dumps(body).encode('utf-8') if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read().decode('utf-8')
                payload = json.loads(content) if content else {}
                if response.status != expected_status:
                    raise CommandError(f'Unexpected MTN response: HTTP {response.status}')
                return response.status, payload
        except urllib.error.HTTPError as exc:
            content = exc.read().decode('utf-8', errors='replace')
            raise CommandError(f'MTN returned HTTP {exc.code}: {content}') from exc
        except urllib.error.URLError as exc:
            raise CommandError(f'Could not connect to MTN: {exc.reason}') from exc
