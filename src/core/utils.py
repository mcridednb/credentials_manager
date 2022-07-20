import logging

import requests

logger = logging.getLogger(__name__)


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def check_proxy(proxy_url):
    response = requests.get("https://api.ipify.org/", proxies={
        "http": proxy_url,
        "https": proxy_url,
    })
    response.raise_for_status()
    return response.text
