# Third Party
from django_celery_beat.models import CrontabSchedule, PeriodicTask

# Django
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Setup periodic tasks for AA TPS"

    def handle(self, *args, **options):
        self.stdout.write("Setting up periodic tasks for AA TPS...")

        # Hourly monthly killmail pull
        hourly_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        PeriodicTask.objects.update_or_create(
            name="AA TPS: Pull Monthly Killmails",
            defaults={
                "task": "aatps.tasks.pull_monthly_killmails",
                "crontab": hourly_schedule,
                "enabled": True,
            },
        )
        self.stdout.write("  - Monthly killmail pull task configured (hourly)")

        # Daily cleanup at 4:30 AM
        cleanup_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="30",
            hour="4",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        PeriodicTask.objects.update_or_create(
            name="AA TPS: Cleanup Old Killmails",
            defaults={
                "task": "aatps.tasks.cleanup_old_killmails",
                "crontab": cleanup_schedule,
                "enabled": True,
            },
        )
        self.stdout.write("  - Cleanup task configured (daily at 4:30 AM)")

        # Remove legacy periodic tasks if they exist
        PeriodicTask.objects.filter(
            name__in=[
                "AA Campaign: Pull ZKillboard Data (Legacy)",
                "AA Campaign: Pull Monthly Killmails",
                "AA Campaign: Cleanup Old Killmails",
            ]
        ).delete()

        self.stdout.write(self.style.SUCCESS("\nSuccessfully setup periodic tasks for AA TPS."))
        self.stdout.write("Please ensure your Celery worker and beat services are running.")
        self.stdout.write("\nTask summary:")
        self.stdout.write("  - Pull Monthly Killmails: Hourly (enabled)")
        self.stdout.write("  - Cleanup Old Killmails: Daily at 4:30 AM (enabled)")
