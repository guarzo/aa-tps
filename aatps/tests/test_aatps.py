"""
AA TPS Test - Monthly Killmail Tests
"""

# Django
from django.test import TestCase
from django.utils import timezone
from aatps.models import MonthlyKillmail, KillmailParticipant
from aatps.tasks import (
    fetch_from_zkill,
    pull_monthly_killmails,
    get_current_month_range,
    get_all_auth_characters,
    get_auth_character_ids,
)
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
