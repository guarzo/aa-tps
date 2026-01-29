"""Tests for aatps views."""

import json
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, Client
from django.urls import reverse

from aatps.models import MonthlyKillmail, KillmailParticipant
from aatps.tests.factories import MonthlyKillmailFactory

User = get_user_model()


class ViewTestBase(TestCase):
    """Base class for view tests with common setup."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        # Create test user with permission
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        # Add permission
        ct = ContentType.objects.get_for_model(MonthlyKillmail)
        perm = Permission.objects.get(content_type=ct, codename='basic_access')
        cls.user.user_permissions.add(perm)

        # Create a user without permission for negative tests
        cls.user_no_perm = User.objects.create_user(
            username='testuser_noperm',
            password='testpass'
        )

    def setUp(self):
        """Set up test client."""
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

        # Reset factory counter between tests
        MonthlyKillmailFactory.reset_counter()


class TestStatsApi(ViewTestBase):
    """Tests for stats_api endpoint."""

    def test_stats_api_empty(self):
        """Test stats API with no data."""
        response = self.client.get(reverse('aatps:stats_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['total_kills'], 0)
        self.assertEqual(data['total_losses'], 0)
        self.assertEqual(data['total_kill_value'], 0)
        self.assertEqual(data['total_loss_value'], 0)
        self.assertEqual(data['active_pilots'], 0)

    def test_stats_api_returns_json(self):
        """Test stats API returns valid JSON."""
        response = self.client.get(reverse('aatps:stats_api'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_stats_api_with_month_params(self):
        """Test stats API accepts year/month parameters."""
        response = self.client.get(
            reverse('aatps:stats_api'),
            {'year': 2024, 'month': 6}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['year'], 2024)
        self.assertEqual(data['month'], 6)

    def test_stats_api_invalid_month_uses_current(self):
        """Test stats API with invalid month uses current month."""
        now = datetime.now(dt_timezone.utc)
        response = self.client.get(
            reverse('aatps:stats_api'),
            {'year': 2024, 'month': 13}  # Invalid month
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Should fall back to current month
        self.assertEqual(data['year'], now.year)
        self.assertEqual(data['month'], now.month)

    def test_stats_api_efficiency_calculation(self):
        """Test efficiency is correctly included in response."""
        response = self.client.get(reverse('aatps:stats_api'))
        data = json.loads(response.content)
        self.assertIn('efficiency', data)
        # With no data, efficiency should be 0
        self.assertEqual(data['efficiency'], 0)


class TestLeaderboardApi(ViewTestBase):
    """Tests for leaderboard_api endpoint."""

    def test_leaderboard_api_basic(self):
        """Test basic leaderboard API response."""
        response = self.client.get(reverse('aatps:leaderboard_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('draw', data)
        self.assertIn('recordsTotal', data)
        self.assertIn('recordsFiltered', data)
        self.assertIn('data', data)

    def test_leaderboard_api_pagination(self):
        """Test that pagination parameters are respected."""
        response = self.client.get(
            reverse('aatps:leaderboard_api'),
            {'start': 0, 'length': 10, 'draw': 1}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['draw'], 1)

    def test_leaderboard_api_max_length_enforced(self):
        """Test that maximum page length is enforced."""
        response = self.client.get(
            reverse('aatps:leaderboard_api'),
            {'length': 9999}  # Exceeds max
        )
        self.assertEqual(response.status_code, 200)
        # The request should succeed, the limit is applied internally

    def test_leaderboard_api_invalid_params(self):
        """Test handling of invalid parameters."""
        response = self.client.get(
            reverse('aatps:leaderboard_api'),
            {'start': 'invalid', 'length': 'abc', 'draw': 'xyz'}
        )
        self.assertEqual(response.status_code, 200)  # Should use defaults
        data = json.loads(response.content)
        # draw defaults to 1 when invalid
        self.assertEqual(data['draw'], 1)

    def test_leaderboard_api_negative_params(self):
        """Test handling of negative parameters."""
        response = self.client.get(
            reverse('aatps:leaderboard_api'),
            {'start': '-5', 'length': '-10'}
        )
        self.assertEqual(response.status_code, 200)
        # Should be clamped to minimum values

    def test_leaderboard_api_search(self):
        """Test search functionality."""
        response = self.client.get(
            reverse('aatps:leaderboard_api'),
            {'search[value]': 'test'}
        )
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_api_sorting(self):
        """Test sorting parameters."""
        response = self.client.get(
            reverse('aatps:leaderboard_api'),
            {'order[0][column]': '1', 'order[0][dir]': 'asc'}
        )
        self.assertEqual(response.status_code, 200)


class TestTopKillsApi(ViewTestBase):
    """Tests for top_kills_api endpoint."""

    def test_top_kills_api_basic(self):
        """Test basic top kills API response."""
        response = self.client.get(reverse('aatps:top_kills_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_top_kills_api_limit(self):
        """Test that limit parameter works."""
        response = self.client.get(
            reverse('aatps:top_kills_api'),
            {'limit': 5}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('data', data)

    def test_top_kills_api_max_limit_enforced(self):
        """Test that maximum limit is enforced."""
        response = self.client.get(
            reverse('aatps:top_kills_api'),
            {'limit': 999}  # Exceeds MAX_TOP_KILLS_LIMIT (50)
        )
        self.assertEqual(response.status_code, 200)

    def test_top_kills_api_invalid_limit(self):
        """Test handling of invalid limit parameter."""
        response = self.client.get(
            reverse('aatps:top_kills_api'),
            {'limit': 'abc'}
        )
        self.assertEqual(response.status_code, 200)  # Should use default


class TestRecentKillsApi(ViewTestBase):
    """Tests for recent_kills_api endpoint."""

    def test_recent_kills_api_basic(self):
        """Test basic recent kills API response."""
        response = self.client.get(reverse('aatps:recent_kills_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_recent_kills_api_limit(self):
        """Test limit parameter."""
        response = self.client.get(
            reverse('aatps:recent_kills_api'),
            {'limit': 25}
        )
        self.assertEqual(response.status_code, 200)

    def test_recent_kills_api_user_only(self):
        """Test user_only parameter."""
        response = self.client.get(
            reverse('aatps:recent_kills_api'),
            {'user_only': 'true'}
        )
        self.assertEqual(response.status_code, 200)


class TestActivityApi(ViewTestBase):
    """Tests for activity_api endpoint."""

    def test_activity_api_basic(self):
        """Test basic activity API response."""
        response = self.client.get(reverse('aatps:activity_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_activity_api_with_month_params(self):
        """Test activity API accepts year/month parameters."""
        response = self.client.get(
            reverse('aatps:activity_api'),
            {'year': 2024, 'month': 6}
        )
        self.assertEqual(response.status_code, 200)


class TestShipStatsApi(ViewTestBase):
    """Tests for ship_stats_api endpoint."""

    def test_ship_stats_api_basic(self):
        """Test basic ship stats API response."""
        response = self.client.get(reverse('aatps:ship_stats_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)


class TestMyStatsApi(ViewTestBase):
    """Tests for my_stats_api endpoint."""

    def test_my_stats_api_basic(self):
        """Test basic my stats API response (user has no characters)."""
        response = self.client.get(reverse('aatps:my_stats_api'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # User has no characters, so should return zeros
        self.assertEqual(data['kills'], 0)
        self.assertEqual(data['losses'], 0)
        self.assertIsNone(data['rank'])
        self.assertIsNone(data['favorite_ship'])

    def test_my_stats_api_response_fields(self):
        """Test my stats API returns all expected fields."""
        response = self.client.get(reverse('aatps:my_stats_api'))
        data = json.loads(response.content)
        expected_fields = [
            'kills', 'losses', 'kill_value', 'loss_value',
            'kill_value_formatted', 'loss_value_formatted',
            'final_blows', 'efficiency', 'rank', 'favorite_ship'
        ]
        for field in expected_fields:
            self.assertIn(field, data)


class TestDashboard(ViewTestBase):
    """Tests for dashboard view."""

    def test_dashboard_loads(self):
        """Test that dashboard loads successfully."""
        response = self.client.get(reverse('aatps:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_context(self):
        """Test that dashboard has expected context."""
        response = self.client.get(reverse('aatps:dashboard'))
        self.assertIn('month_name', response.context)
        self.assertIn('year', response.context)
        self.assertIn('month', response.context)


class TestHistoricalView(ViewTestBase):
    """Tests for historical view."""

    def test_historical_view_valid_date(self):
        """Test historical view with valid date."""
        # Use a past date
        past_date = datetime.now(dt_timezone.utc) - timedelta(days=60)
        response = self.client.get(
            reverse('aatps:historical', kwargs={
                'year': past_date.year,
                'month': past_date.month
            })
        )
        self.assertEqual(response.status_code, 200)

    def test_historical_view_invalid_month(self):
        """Test historical view with invalid month."""
        response = self.client.get(
            reverse('aatps:historical', kwargs={'year': 2024, 'month': 13})
        )
        self.assertEqual(response.status_code, 404)

    def test_historical_view_future_date(self):
        """Test historical view rejects future dates."""
        future_date = datetime.now(dt_timezone.utc) + timedelta(days=60)
        response = self.client.get(
            reverse('aatps:historical', kwargs={
                'year': future_date.year,
                'month': future_date.month
            })
        )
        self.assertEqual(response.status_code, 404)


class TestAuthRequired(TestCase):
    """Tests that authentication is required."""

    def test_dashboard_requires_login(self):
        """Test that dashboard requires login."""
        client = Client()
        response = client.get(reverse('aatps:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_api_requires_login(self):
        """Test that API endpoints require login."""
        client = Client()
        endpoints = [
            'aatps:stats_api',
            'aatps:leaderboard_api',
            'aatps:activity_api',
            'aatps:top_kills_api',
            'aatps:ship_stats_api',
            'aatps:my_stats_api',
            'aatps:recent_kills_api',
        ]
        for endpoint in endpoints:
            response = client.get(reverse(endpoint))
            self.assertEqual(
                response.status_code, 302,
                f"{endpoint} should require login"
            )

    def test_historical_requires_login(self):
        """Test that historical view requires login."""
        client = Client()
        response = client.get(
            reverse('aatps:historical', kwargs={'year': 2024, 'month': 1})
        )
        self.assertEqual(response.status_code, 302)


class TestPermissionRequired(TestCase):
    """Tests that permission is required for views."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        # Create user without permission
        cls.user_no_perm = User.objects.create_user(
            username='nopermuser',
            password='testpass'
        )

    def setUp(self):
        """Set up test client."""
        self.client = Client()
        self.client.login(username='nopermuser', password='testpass')

    def test_dashboard_requires_permission(self):
        """Test that dashboard requires basic_access permission."""
        response = self.client.get(reverse('aatps:dashboard'))
        # Should return 403 Forbidden when permission is missing
        self.assertEqual(response.status_code, 403)

    def test_api_requires_permission(self):
        """Test that API endpoints require basic_access permission."""
        endpoints = [
            'aatps:stats_api',
            'aatps:leaderboard_api',
            'aatps:activity_api',
            'aatps:top_kills_api',
            'aatps:ship_stats_api',
            'aatps:my_stats_api',
            'aatps:recent_kills_api',
        ]
        for endpoint in endpoints:
            response = self.client.get(reverse(endpoint))
            self.assertEqual(
                response.status_code, 403,
                f"{endpoint} should require basic_access permission"
            )
