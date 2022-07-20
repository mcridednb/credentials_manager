from django.core.management.base import BaseCommand

from core.tasks import update_proxy_statuses


class Command(BaseCommand):
    help = 'Обновление статусов прокси'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Обновить статус всех прокси',
        )

    def handle(self, *args, **options):
        update_proxy_statuses.delay(**options)

        self.stdout.write(self.style.SUCCESS(
            "Статусы прокси обновлены"
        ))
