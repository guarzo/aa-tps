from django.core.management.base import BaseCommand
from django.db.models import Q
from aacampaign.tasks import pull_zkillboard_data, repair_killmail_by_id
from aacampaign.models import CampaignKillmail

class Command(BaseCommand):
    help = 'Manually trigger pulling ZKillboard data or repairing existing data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--seconds',
            type=int,
            help='Pull data for the last X seconds',
        )
        parser.add_argument(
            '--days',
            type=int,
            help='Pull data for the last X days',
        )
        parser.add_argument(
            '--repair',
            action='store_true',
            help='Attempt to repair existing killmails with missing ship information',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed debug information during the pull',
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose')
        if verbose:
            import logging
            logging.getLogger('aacampaign').setLevel(logging.DEBUG)

        if options.get('repair'):
            kms_to_repair = list(CampaignKillmail.objects.filter(
                Q(ship_type_id=0) |
                Q(ship_group_name="Unknown") |
                Q(final_blow_char_id=0, final_blow_corp_id=0) |
                Q(final_blow_char_name="", final_blow_char_id__gt=0) |
                Q(final_blow_corp_name="Unknown", final_blow_corp_id__gt=0)
            ).values_list('killmail_id', flat=True).distinct())
            total = len(kms_to_repair)
            if total == 0:
                self.stdout.write(self.style.SUCCESS("No killmails found in need of repair"))
                return

            self.stdout.write(f"Repairing {total} killmails with missing ship information...")
            repaired_count = 0
            for i, km_id in enumerate(kms_to_repair, 1):
                if repair_killmail_by_id(km_id):
                    repaired_count += 1

                # Progress indicator
                self.stdout.write(f"Progress: [{i}/{total}]", ending='\r')
                self.stdout.flush()

            self.stdout.write("") # newline
            self.stdout.write(self.style.SUCCESS(f"Finished: Repaired {repaired_count} killmails"))
            return

        seconds = options.get('seconds')
        days = options.get('days')
        if days:
            seconds = days * 86400

        if seconds:
            self.stdout.write(f"Triggering ZKillboard data pull for the last {seconds} seconds...")
        else:
            self.stdout.write("Triggering ZKillboard data pull (defaulting to today's data)...")

        result = pull_zkillboard_data(past_seconds=seconds)
        self.stdout.write(self.style.SUCCESS(f"Finished: {result}"))
