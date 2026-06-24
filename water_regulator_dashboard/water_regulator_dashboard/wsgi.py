import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'water_regulator_dashboard.settings')
application = get_wsgi_application()
