# Standard Library
import logging

# Django
from django.core.management.base import BaseCommand

# AA Campaign
from aatps.tasks import (
    get_current_month_range,
    pull_monthly_killmails,
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
    # Always silence the noisy ESI/HTTP client loggers
    for logger_name in (
        "esi",
        "esi.aiopenapi3",
        "esi.openapi_clients",
        "httpx",
        "urllib3",
        "requests",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    if verbose:
        logging.getLogger("aatps").setLevel(logging.DEBUG)
    else:
        logging.getLogger("aatps").setLevel(logging.INFO)


class Command(BaseCommand):
    help = "Manually trigger pulling killmail data for all authenticated users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed debug information during the pull",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Clear any existing task lock and force a new run",
        )
        parser.add_argument(
            "--clear-lock",
            action="store_true",
            help="Only clear the task lock without running the pull",
        )

    def handle(self, *args, **options):
        verbose = options.get("verbose")
        force = options.get("force")
        clear_lock = options.get("clear_lock")
        _configure_logging(verbose)

        lock_id = "aatps-pull-monthly-killmails-lock"

        if clear_lock or force:
            from django.core.cache import cache
            if cache.get(lock_id):
                cache.delete(lock_id)
                self.stdout.write(self.style.SUCCESS("Cleared existing task lock."))
            else:
                self.stdout.write("No lock found.")

            if clear_lock:
                return

        self._handle_monthly_pull()

    def _handle_monthly_pull(self):
        """Handle monthly killmail pull for all auth users."""
        month_start, month_end = get_current_month_range()
        month_name = month_start.strftime("%B %Y")

        self.stdout.write(f"Pulling monthly killmails for {month_name}...")
        self.stdout.write("This will pull killmails for all authenticated users.")

        result = pull_monthly_killmails()
        self.stdout.write(self.style.SUCCESS(f"Finished: {result}"))
