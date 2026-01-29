import logging
from django.core.management.base import BaseCommand
from aatps.tasks import (
    pull_monthly_killmails,
    get_current_month_range,
)


class _AatpsPullLogFilter(logging.Filter):
    def filter(self, record):
        if record.levelno >= logging.ERROR:
            return True
        message = record.getMessage()
        return (
            message.startswith("ESI rate limit remaining")
            or message.startswith("ESI rate limit hit")
            or message.startswith("ESI rate limit remaining low")
        )


def _configure_logging(verbose):
    if verbose:
        logging.getLogger('aatps').setLevel(logging.DEBUG)
        return

    logging.getLogger('aatps').setLevel(logging.INFO)
    for logger_name in (
        'esi',
        'esi.aiopenapi3',
        'esi.openapi_clients',
        'httpx',
        'urllib3',
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)

    log_filter = _AatpsPullLogFilter()
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, _AatpsPullLogFilter) for f in handler.filters):
            handler.addFilter(log_filter)
    for handler in logging.getLogger('aatps').handlers:
        if not any(isinstance(f, _AatpsPullLogFilter) for f in handler.filters):
            handler.addFilter(log_filter)


class Command(BaseCommand):
    help = 'Manually trigger pulling killmail data for all authenticated users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed debug information during the pull',
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose')
        _configure_logging(verbose)

        self._handle_monthly_pull()

    def _handle_monthly_pull(self):
        """Handle monthly killmail pull for all auth users."""
        month_start, month_end = get_current_month_range()
        month_name = month_start.strftime('%B %Y')

        self.stdout.write(f"Pulling monthly killmails for {month_name}...")
        self.stdout.write("This will pull killmails for all authenticated users.")

        result = pull_monthly_killmails()
        self.stdout.write(self.style.SUCCESS(f"Finished: {result}"))
