import logging

import requests

logger = logging.getLogger(__name__)


def check_proxy(proxy_url):
    response = requests.get("https://api.ipify.org/", proxies={
        "http": proxy_url,
        "https": proxy_url,
    })
    response.raise_for_status()
    return response.text


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
