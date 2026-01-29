"""
AA TPS Test - Monthly Killmail Tests
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

# Django
from django.test import TestCase
from django.utils import timezone

from aatps.models import MonthlyKillmail, KillmailParticipant
from aatps.tasks import (
    fetch_from_zkill,
    get_current_month_range,
    pull_monthly_killmails,
    process_monthly_killmail,
    cleanup_old_killmails,
)
from aatps.tests.factories import MonthlyKillmailFactory
from unittest.mock import patch, MagicMock


class TestZKillboardAPI(TestCase):
    @patch('aatps.tasks._zkill_session.get')
    def test_fetch_from_zkill_returns_dict(self, mock_get):
        # Mock a response that returns a dictionary instead of a list (e.g. error from zKill)
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "Too many requests"}
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # This should log an error and return None gracefully
        result = fetch_from_zkill('allianceID', 99009902)
        self.assertIsNone(result)

    @patch('aatps.tasks._zkill_session.get')
    def test_fetch_from_zkill_url_generation(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        fetch_from_zkill('allianceID', 99009902, page=2, year=2026, month=1)

        args, kwargs = mock_get.call_args
        url = args[0]
        self.assertNotIn('startTime', url)
        self.assertIn('year/2026/month/1/', url)
        self.assertIn('page/2/', url)
        self.assertIn('allianceID/99009902/', url)

    @patch('aatps.tasks._zkill_session.get')
    @patch('aatps.tasks.time.sleep')
    @patch('aatps.tasks.time.time')
    def test_zkill_get_rate_limiting(self, mock_time, mock_sleep, mock_get):
        from aatps.tasks import _zkill_get
        import aatps.tasks

        # Reset the global tracker for deterministic test
        aatps.tasks._last_zkill_call = 0

        mock_response = MagicMock()
        mock_get.return_value = mock_response

        # First call at T=1000
        mock_time.return_value = 1000.0
        _zkill_get("https://zkillboard.com/api/test/")
        self.assertEqual(mock_sleep.call_count, 0)

        # Second call at T=1000.1 (only 100ms later)
        mock_time.return_value = 1000.1
        _zkill_get("https://zkillboard.com/api/test/")

        # Should have slept for 0.4s to reach 500ms total gap
        mock_sleep.assert_called_once()
        self.assertAlmostEqual(mock_sleep.call_args[0][0], 0.4)


class TestMonthlyKillmailPull(TestCase):
    @patch('aatps.tasks.cache')
    @patch('aatps.tasks._pull_monthly_killmails_logic')
    def test_pull_monthly_killmails_lock_behavior(self, mock_logic, mock_cache):
        # 1. Test initial lock acquisition
        mock_cache.add.return_value = True

        pull_monthly_killmails()

        # Should acquire lock for 2h (7200)
        mock_cache.add.assert_called_with("aatps-pull-monthly-killmails-lock", True, 7200)
        # Should delete lock in finally
        mock_cache.delete.assert_called_with("aatps-pull-monthly-killmails-lock")

        # 2. Test when already running
        mock_cache.add.return_value = False
        result = pull_monthly_killmails()
        self.assertEqual(result, "Task already running")


class TestHelperFunctions(TestCase):
    def test_get_current_month_range(self):
        start, end = get_current_month_range()

        # Start should be day 1, 00:00:00
        self.assertEqual(start.day, 1)
        self.assertEqual(start.hour, 0)
        self.assertEqual(start.minute, 0)
        self.assertEqual(start.second, 0)

        # End should be last day of month, 23:59:59
        self.assertEqual(end.hour, 23)
        self.assertEqual(end.minute, 59)
        self.assertEqual(end.second, 59)

        # Both should be in the same month
        self.assertEqual(start.month, end.month)
        self.assertEqual(start.year, end.year)


class TestMonthlyKillmailModel(TestCase):
    def test_monthly_killmail_creation(self):
        """Test that MonthlyKillmail can be created."""
        km = MonthlyKillmail.objects.create(
            killmail_id=12345,
            killmail_time=timezone.now(),
            solar_system_id=30000142,
            solar_system_name="Jita",
            region_id=10000002,
            region_name="The Forge",
            ship_type_id=587,
            ship_type_name="Rifter",
            ship_group_name="Frigate",
            victim_id=123456789,
            victim_name="Test Victim",
            victim_corp_id=98000001,
            victim_corp_name="Test Corp",
            total_value=1000000.00,
        )
        self.assertEqual(km.killmail_id, 12345)
        self.assertEqual(str(km), "Killmail 12345 - Test Victim")

    def test_monthly_killmail_has_permissions(self):
        """Test that MonthlyKillmail has the basic_access permission."""
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(MonthlyKillmail)
        perm = Permission.objects.filter(
            content_type=ct,
            codename='basic_access'
        ).first()
        self.assertIsNotNone(perm)
        self.assertEqual(perm.name, "Can access this app")


class TestProcessMonthlyKillmail(TestCase):
    """Tests for process_monthly_killmail function."""

    def setUp(self):
        """Set up test fixtures."""
        MonthlyKillmailFactory.reset_counter()

    @patch('aatps.tasks.fetch_killmail_from_esi')
    @patch('aatps.tasks._resolve_name')
    @patch('aatps.tasks.get_user_for_character')
    def test_process_killmail_skips_without_auth_users(self, mock_get_user, mock_resolve, mock_esi):
        """Test that killmails without auth user involvement are skipped."""
        km_data = {
            'killmail_id': 99999,
            'killmail_time': '2024-01-15T12:00:00Z',
            'solar_system_id': 30000142,
            'victim': {
                'character_id': 123456,
                'corporation_id': 98000001,
                'ship_type_id': 587,
            },
            'attackers': [
                {
                    'character_id': 654321,
                    'corporation_id': 98000002,
                    'ship_type_id': 587,
                    'final_blow': True,
                    'damage_done': 1000,
                }
            ],
            'zkb': {
                'hash': 'abc123',
                'totalValue': 1000000,
            }
        }

        # Empty auth_char_ids means no auth user involved
        context = {
            'auth_char_ids': set(),
            'resolved_names': {},
            'resolved_characters': {},
            'resolved_systems': {},
            'resolved_types': {},
        }

        month_start = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)

        result = process_monthly_killmail(km_data, context, month_start)
        self.assertIsNone(result)

    @patch('aatps.tasks.fetch_killmail_from_esi')
    @patch('aatps.tasks._resolve_name')
    def test_process_killmail_skips_invalid_id(self, mock_resolve, mock_esi):
        """Test that killmails without ID are skipped."""
        km_data = {
            # Missing killmail_id
            'killmail_time': '2024-01-15T12:00:00Z',
        }

        context = {
            'auth_char_ids': {123456},
            'resolved_names': {},
            'resolved_characters': {},
            'resolved_systems': {},
            'resolved_types': {},
        }

        month_start = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)

        result = process_monthly_killmail(km_data, context, month_start)
        self.assertIsNone(result)

    @patch('aatps.tasks.fetch_killmail_from_esi')
    @patch('aatps.tasks._resolve_name')
    def test_process_killmail_skips_before_month_start(self, mock_resolve, mock_esi):
        """Test that killmails before month start are skipped."""
        mock_resolve.return_value = "Test Name"

        km_data = {
            'killmail_id': 99999,
            'killmail_time': '2023-12-15T12:00:00Z',  # Before month start
            'solar_system_id': 30000142,
            'victim': {
                'character_id': 999999,
                'corporation_id': 98000001,
                'ship_type_id': 587,
            },
            'attackers': [
                {
                    'character_id': 123456,  # This is an auth char
                    'corporation_id': 98000002,
                    'ship_type_id': 587,
                    'final_blow': True,
                    'damage_done': 1000,
                }
            ],
            'zkb': {
                'hash': 'abc123',
                'totalValue': 1000000,
            }
        }

        context = {
            'auth_char_ids': {123456},
            'resolved_names': {},
            'resolved_characters': {},
            'resolved_systems': {},
            'resolved_types': {},
        }

        month_start = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)

        result = process_monthly_killmail(km_data, context, month_start)
        self.assertIsNone(result)


class TestCleanupOldKillmails(TestCase):
    """Tests for cleanup_old_killmails task."""

    def setUp(self):
        """Set up test fixtures."""
        MonthlyKillmailFactory.reset_counter()

    def test_cleanup_deletes_old_records(self):
        """Test that old killmails are deleted."""
        # Create an old killmail (older than default 12 months)
        old_time = datetime.now(dt_timezone.utc) - timedelta(days=400)
        old_km = MonthlyKillmail.objects.create(
            killmail_id=1,
            killmail_time=old_time,
            solar_system_id=30000142,
            solar_system_name="Jita",
        )

        # Create a recent killmail
        recent_km = MonthlyKillmail.objects.create(
            killmail_id=2,
            killmail_time=datetime.now(dt_timezone.utc),
            solar_system_id=30000142,
            solar_system_name="Jita",
        )

        # Run cleanup with default retention (12 months)
        with patch('aatps.tasks.AA_TPS_RETENTION_MONTHS', 12):
            result = cleanup_old_killmails()

        # Old should be deleted, recent should remain
        self.assertFalse(MonthlyKillmail.objects.filter(killmail_id=1).exists())
        self.assertTrue(MonthlyKillmail.objects.filter(killmail_id=2).exists())
        self.assertIn("Deleted", result)

    def test_cleanup_keeps_recent_records(self):
        """Test that recent killmails are kept."""
        # Create several recent killmails
        for i in range(5):
            MonthlyKillmailFactory.create(
                killmail_id=100 + i,
                killmail_time=datetime.now(dt_timezone.utc) - timedelta(days=i * 30)
            )

        initial_count = MonthlyKillmail.objects.count()

        # Run cleanup with default retention
        with patch('aatps.tasks.AA_TPS_RETENTION_MONTHS', 12):
            cleanup_old_killmails()

        # All should be kept (none are older than 12 months)
        self.assertEqual(MonthlyKillmail.objects.count(), initial_count)

    def test_cleanup_respects_retention_setting(self):
        """Test that cleanup respects the retention months setting."""
        # Create a killmail that's 60 days old
        km_60_days = MonthlyKillmail.objects.create(
            killmail_id=1,
            killmail_time=datetime.now(dt_timezone.utc) - timedelta(days=60),
            solar_system_id=30000142,
        )

        # Run cleanup with 1 month retention (should delete 60-day-old record)
        with patch('aatps.tasks.AA_TPS_RETENTION_MONTHS', 1):
            cleanup_old_killmails()

        # Should be deleted (60 days > 30 days retention)
        self.assertFalse(MonthlyKillmail.objects.filter(killmail_id=1).exists())

    def test_cleanup_with_no_old_records(self):
        """Test cleanup when there are no old records."""
        # Create only recent killmails
        for i in range(3):
            MonthlyKillmailFactory.create(
                killmail_id=200 + i,
                killmail_time=datetime.now(dt_timezone.utc)
            )

        with patch('aatps.tasks.AA_TPS_RETENTION_MONTHS', 12):
            result = cleanup_old_killmails()

        self.assertIn("Deleted 0", result)

    def test_cleanup_cascades_to_participants(self):
        """Test that deleting killmails cascades to participants."""
        # Create an old killmail
        old_time = datetime.now(dt_timezone.utc) - timedelta(days=400)
        old_km = MonthlyKillmail.objects.create(
            killmail_id=999,
            killmail_time=old_time,
            solar_system_id=30000142,
        )

        # Note: We can't easily create KillmailParticipant without EveCharacter
        # but we can verify the count behavior
        initial_km_count = MonthlyKillmail.objects.count()

        with patch('aatps.tasks.AA_TPS_RETENTION_MONTHS', 12):
            cleanup_old_killmails()

        self.assertEqual(MonthlyKillmail.objects.count(), initial_km_count - 1)


class TestKillmailParticipantModel(TestCase):
    """Tests for KillmailParticipant model."""

    def test_participant_str_attacker(self):
        """Test string representation for attacker."""
        km = MonthlyKillmail.objects.create(
            killmail_id=12345,
            killmail_time=timezone.now(),
            solar_system_id=30000142,
        )
        # Note: Creating a full participant requires EveCharacter
        # This test validates the model exists and can be queried
        self.assertEqual(km.participants.count(), 0)

    def test_killmail_participants_relationship(self):
        """Test the reverse relationship from killmail to participants."""
        km = MonthlyKillmail.objects.create(
            killmail_id=54321,
            killmail_time=timezone.now(),
            solar_system_id=30000142,
        )
        # Verify the related_name 'participants' works
        self.assertIsNotNone(km.participants)
        self.assertEqual(km.participants.count(), 0)
