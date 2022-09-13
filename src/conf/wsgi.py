"""
WSGI config for credentials_manager project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
import django.http.request
from django.utils.regex_helper import _lazy_re_compile

django.http.request.host_validation_re = _lazy_re_compile(r"[a-zA-z0-9:]*")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conf.settings')

application = get_wsgi_application()
