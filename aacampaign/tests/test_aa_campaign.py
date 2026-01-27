"""
AA Campaign Test
"""

# Django
from django.test import TestCase
from django.utils import timezone
from aacampaign.models import Campaign, CampaignMember, CampaignKillmail, CampaignTarget
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo, EveAllianceInfo
from eveuniverse.models import EveSolarSystem, EveConstellation, EveRegion
from aacampaign.tasks import should_include_killmail, process_killmail, fetch_from_zkill, pull_zkillboard_data
from unittest.mock import patch, MagicMock

class TestZKillboardAPI(TestCase):
    @patch('aacampaign.tasks._zkill_session.get')
    def test_fetch_from_zkill_returns_dict(self, mock_get):
        # Mock a response that returns a dictionary instead of a list (e.g. error from zKill)
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "Too many requests"}
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        # This should log an error and return None gracefully
        result = fetch_from_zkill('allianceID', 99009902)
        self.assertIsNone(result)

    @patch('aacampaign.tasks._zkill_session.get')
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

    @patch('aacampaign.tasks.fetch_from_zkill')
    def test_pull_zkillboard_data_uses_paging_for_past_seconds(self, mock_fetch):
        # Setup a campaign and entity
        campaign = Campaign.objects.create(
            name="Test Campaign",
            start_date=timezone.now() - timezone.timedelta(days=30),
            is_active=True
        )
        alliance = EveAllianceInfo.objects.create(alliance_id=99009902, alliance_name="Test Alliance", executor_corp_id=1)
        CampaignMember.objects.create(campaign=campaign, alliance=alliance)

        mock_fetch.return_value = []

        # Call with large past_seconds (23 days)
        pull_zkillboard_data(past_seconds=1987200)

        # Check that it called fetch_from_zkill with page=1, NOT past_seconds
        # This verifies the fix for large past_seconds values
        _, kwargs = mock_fetch.call_args_list[0]
        self.assertIn('page', kwargs)
        self.assertEqual(kwargs['page'], 1)
        self.assertNotIn('past_seconds', kwargs)

    @patch('aacampaign.tasks.fetch_from_zkill')
    def test_pull_zkillboard_data_uses_past_seconds_for_small_values(self, mock_fetch):
        # Setup a campaign and entity
        campaign = Campaign.objects.create(
            name="Test Campaign",
            start_date=timezone.now() - timezone.timedelta(hours=1),
            is_active=True
        )
        alliance = EveAllianceInfo.objects.create(alliance_id=99009902, alliance_name="Test Alliance", executor_corp_id=1)
        CampaignMember.objects.create(campaign=campaign, alliance=alliance)

        mock_fetch.return_value = []

        # Call without past_seconds (should use default lookback which is 1h since campaign is new)
        pull_zkillboard_data()

        # Check that it called fetch_from_zkill with past_seconds
        _, kwargs = mock_fetch.call_args_list[0]
        self.assertIn('past_seconds', kwargs)
        self.assertLessEqual(kwargs['past_seconds'], 3660) # 1h + small buffer
        self.assertGreaterEqual(kwargs['past_seconds'], 3540)

    @patch('aacampaign.tasks.fetch_from_zkill')
    def test_pull_zkillboard_data_updates_last_run(self, mock_fetch):
        # Setup a campaign
        campaign = Campaign.objects.create(
            name="Test Campaign",
            start_date=timezone.now() - timezone.timedelta(hours=1),
            is_active=True
        )
        mock_fetch.return_value = []

        self.assertIsNone(campaign.last_run)

        pull_zkillboard_data()

        campaign.refresh_from_db()
        self.assertIsNotNone(campaign.last_run)

    @patch('aacampaign.tasks.cache')
    @patch('aacampaign.tasks._pull_zkillboard_data_logic')
    def test_pull_zkillboard_data_lock_behavior(self, mock_logic, mock_cache):
        # 1. Test initial lock acquisition
        mock_cache.add.return_value = True

        pull_zkillboard_data()

        # Should acquire lock for 2h (7200)
        mock_cache.add.assert_called_with("aacampaign-pull-zkillboard-data-lock", True, 7200)
        # Should delete lock in finally
        mock_cache.delete.assert_called_with("aacampaign-pull-zkillboard-data-lock")

        # 2. Test when already running
        mock_cache.add.return_value = False
        result = pull_zkillboard_data()
        self.assertEqual(result, "Task already running")

    @patch('aacampaign.tasks.cache')
    @patch('aacampaign.tasks.fetch_from_zkill')
    @patch('aacampaign.tasks.time.time')
    def test_pull_zkillboard_data_timeout(self, mock_time, mock_fetch, mock_cache):
        # Setup a campaign and entity to trigger the loop
        campaign = Campaign.objects.create(
            name="Test Campaign",
            start_date=timezone.now() - timezone.timedelta(hours=1),
            is_active=True
        )
        alliance = EveAllianceInfo.objects.create(alliance_id=99009902, alliance_name="Test Alliance", executor_corp_id=1)
        CampaignMember.objects.create(campaign=campaign, alliance=alliance)

        mock_cache.add.return_value = True
        mock_fetch.return_value = []

        # T=0 (start), T=7300 (loop iteration check - triggers timeout)
        mock_time.side_effect = [0, 7300, 7300, 7300, 7300]

        pull_zkillboard_data()

        # Should NOT have called fetch due to timeout
        self.assertEqual(mock_fetch.call_count, 0)

    @patch('aacampaign.tasks.fetch_from_zkill')
    def test_pull_zkillboard_data_optimization(self, mock_fetch):
        # Setup a campaign with filters (targets and locations)
        campaign = Campaign.objects.create(
            name="Filtered Campaign",
            start_date=timezone.now() - timezone.timedelta(days=1),
            is_active=True
        )

        # Friendly member (should NOT be pulled because we have filters)
        alliance_friendly = EveAllianceInfo.objects.create(alliance_id=1, alliance_name="Friendly Alliance", executor_corp_id=1)
        CampaignMember.objects.create(campaign=campaign, alliance=alliance_friendly)

        # Target (should be pulled)
        alliance_target = EveAllianceInfo.objects.create(alliance_id=2, alliance_name="Target Alliance", executor_corp_id=2)
        CampaignTarget.objects.create(campaign=campaign, alliance=alliance_target)

        # Location (should be pulled)
        region = EveRegion.objects.create(id=10, name="Target Region")
        campaign.regions.add(region)

        mock_fetch.return_value = []

        pull_zkillboard_data()

        # Should have called fetch for:
        # 1. Target Alliance (allianceID, 2)
        # 2. Target Region (regionID, 10)
        # Should NOT have called for Friendly Alliance (allianceID, 1)

        called_entities = [(args[0], args[1]) for args, _ in mock_fetch.call_args_list]
        self.assertIn(('allianceID', 2), called_entities)
        self.assertIn(('regionID', 10), called_entities)
        self.assertNotIn(('allianceID', 1), called_entities)

    @patch('aacampaign.tasks.fetch_from_zkill')
    def test_pull_zkillboard_data_hierarchy_deduplication(self, mock_fetch):
        # Global campaign (no filters)
        campaign = Campaign.objects.create(
            name="Global Campaign",
            start_date=timezone.now() - timezone.timedelta(days=1),
            is_active=True
        )

        # Alliance, Corp (in Alliance), Char (in Corp)
        alliance = EveAllianceInfo.objects.create(alliance_id=100, alliance_name="A", executor_corp_id=101)
        corp = EveCorporationInfo.objects.create(corporation_id=101, corporation_name="C", member_count=1, alliance=alliance)
        char = EveCharacter.objects.create(character_id=1001, character_name="Ch", corporation_id=101, alliance_id=100)

        CampaignMember.objects.create(campaign=campaign, alliance=alliance)
        CampaignMember.objects.create(campaign=campaign, corporation=corp)
        CampaignMember.objects.create(campaign=campaign, character=char)

        mock_fetch.return_value = []

        pull_zkillboard_data()

        # Should only pull for the Alliance
        called_entities = [(args[0], args[1]) for args, _ in mock_fetch.call_args_list]
        self.assertIn(('allianceID', 100), called_entities)
        self.assertNotIn(('corporationID', 101), called_entities)
        self.assertNotIn(('characterID', 1001), called_entities)

    @patch('aacampaign.tasks._zkill_session.get')
    @patch('aacampaign.tasks.time.sleep')
    @patch('aacampaign.tasks.time.time')
    def test_zkill_get_rate_limiting(self, mock_time, mock_sleep, mock_get):
        from aacampaign.tasks import _zkill_get
        import aacampaign.tasks

        # Reset the global tracker for deterministic test
        aacampaign.tasks._last_zkill_call = 0

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
        # Use almost equal for float comparison if needed, but here it's exact subtraction
        self.assertAlmostEqual(mock_sleep.call_args[0][0], 0.4)

    @patch('aacampaign.tasks.cache')
    def test_repair_campaign_killmails_lock(self, mock_cache):
        from aacampaign.tasks import repair_campaign_killmails

        # 1. Test acquisition
        mock_cache.add.return_value = True

        repair_campaign_killmails()

        # Should use 7200s
        mock_cache.add.assert_called_with("aacampaign-repair-campaign-killmails-lock", True, 7200)
        mock_cache.delete.assert_called_with("aacampaign-repair-campaign-killmails-lock")

        # 2. Test already running
        mock_cache.add.return_value = False
        result = repair_campaign_killmails()
        self.assertEqual(result, "Task already running")

class TestCampaign(TestCase):
    def setUp(self):
        # Setup basic universe
        self.region = EveRegion.objects.create(id=10000001, name="Test Region")
        self.constellation = EveConstellation.objects.create(id=20000001, name="Test Const", eve_region=self.region)
        self.system = EveSolarSystem.objects.create(id=30000001, name="Test System", eve_constellation=self.constellation, security_status=0.5)

        # Setup characters
        self.char1 = EveCharacter.objects.create(character_id=1, character_name="Friendly Char", corporation_id=10, corporation_name="Friendly Corp")

        # Setup campaign
        self.campaign = Campaign.objects.create(
            name="Test Campaign",
            start_date=timezone.now() - timezone.timedelta(days=1),
            is_active=True
        )
        self.campaign.systems.add(self.system)
        CampaignMember.objects.create(campaign=self.campaign, character=self.char1)

    def test_should_include_killmail_friendly_attacker(self):
        km_data = {
            'killmail_id': 12345,
            'killmail_time': timezone.now().isoformat(),
            'solar_system_id': 30000001,
            'attackers': [{'character_id': 1, 'final_blow': True}],
            'victim': {'character_id': 2}
        }
        self.assertTrue(should_include_killmail(self.campaign, km_data))

    def test_should_include_killmail_wrong_location(self):
        km_data = {
            'killmail_id': 12345,
            'killmail_time': timezone.now().isoformat(),
            'solar_system_id': 30000002,
            'attackers': [{'character_id': 1}],
            'victim': {'character_id': 2}
        }
        self.assertFalse(should_include_killmail(self.campaign, km_data))

    def test_should_include_killmail_regional_with_target_outside(self):
        char_target = EveCharacter.objects.create(character_id=3, character_name="Target", corporation_id=30, corporation_name="TCorp")
        CampaignTarget.objects.create(campaign=self.campaign, character=char_target)

        # Kill outside region, but it's a target
        km_data = {
            'killmail_id': 12346,
            'killmail_time': timezone.now().isoformat(),
            'solar_system_id': 30000002,
            'attackers': [{'character_id': 1, 'final_blow': True}],
            'victim': {'character_id': 3}
        }
        self.assertTrue(should_include_killmail(self.campaign, km_data))

    @patch('aacampaign.tasks.EveType.objects.get_or_create_esi')
    @patch('aacampaign.tasks.EveCharacter.objects.create_character')
    @patch('aacampaign.tasks.EveEntity.objects.get_or_create_esi')
    def test_process_killmail(self, mock_get_or_create_esi, mock_create_char, mock_get_type):
        mock_entity = MagicMock()
        mock_entity.name = 'Resolved Name'
        mock_get_or_create_esi.return_value = (mock_entity, True)
        mock_create_char.return_value = self.char1

        mock_type = MagicMock()
        mock_type.eve_group.name = 'Test Group'
        mock_get_type.return_value = (mock_type, True)

        km_data = {
            'killmail_id': 12345,
            'killmail_time': timezone.now().isoformat(),
            'solar_system_id': 30000001,
            'attackers': [{'character_id': 1, 'final_blow': True}],
            'victim': {
                'character_id': 2,
                'corporation_id': 20,
                'ship_type_id': 601,
            },
            'zkb': {'totalValue': 1000000}
        }
        process_killmail(self.campaign, km_data)

        ckm = CampaignKillmail.objects.get(killmail_id=12345)
        self.assertEqual(ckm.total_value, 1000000)
        self.assertIn(self.char1, ckm.attackers.all())
        self.assertFalse(ckm.is_loss)
        self.assertEqual(ckm.victim_name, 'Resolved Name')
        self.assertEqual(ckm.ship_group_name, 'Test Group')

    @patch('aacampaign.tasks.EveType.objects.get_or_create_esi')
    @patch('aacampaign.tasks.EveCharacter.objects.create_character')
    @patch('aacampaign.tasks.EveEntity.objects.get_or_create_esi')
    def test_process_killmail_corp_member(self, mock_get_or_create_esi, mock_create_char, mock_get_type):
        mock_entity = MagicMock()
        mock_entity.name = 'Resolved Name'
        mock_get_or_create_esi.return_value = (mock_entity, True)

        mock_type = MagicMock()
        mock_type.eve_group.name = 'Test Group'
        mock_get_type.return_value = (mock_type, True)

        corp = EveCorporationInfo.objects.create(corporation_id=100, corporation_name="Member Corp", member_count=1)
        CampaignMember.objects.create(campaign=self.campaign, corporation=corp)

        # Character in the corp but not specifically in campaign members
        char_in_corp = EveCharacter.objects.create(character_id=101, character_name="Corp Member", corporation_id=100, corporation_name="Member Corp")
        mock_create_char.return_value = char_in_corp

        km_data = {
            'killmail_id': 12347,
            'killmail_time': timezone.now().isoformat(),
            'solar_system_id': 30000001,
            'attackers': [{'character_id': 101, 'corporation_id': 100, 'final_blow': True}],
            'victim': {'character_id': 2},
            'zkb': {'totalValue': 1000000}
        }
        process_killmail(self.campaign, km_data)

        ckm = CampaignKillmail.objects.get(killmail_id=12347)
        self.assertIn(char_in_corp, ckm.attackers.all())

class TestGlobalCampaign(TestCase):
    def setUp(self):
        self.char_friendly = EveCharacter.objects.create(character_id=1, character_name="Friendly", corporation_id=10, corporation_name="FCorp")
        self.char_target = EveCharacter.objects.create(character_id=3, character_name="Target", corporation_id=30, corporation_name="TCorp")

        self.campaign = Campaign.objects.create(
            name="Global Campaign",
            start_date=timezone.now() - timezone.timedelta(days=1),
            is_active=True
        )
        CampaignMember.objects.create(campaign=self.campaign, character=self.char_friendly)
        CampaignTarget.objects.create(campaign=self.campaign, character=self.char_target)

    def test_should_include_killmail_global_match(self):
        # Friendly kills Target outside of any specific location
        km_data = {
            'killmail_id': 20001,
            'killmail_time': timezone.now().isoformat(),
            'solar_system_id': 99999999, # Random system
            'attackers': [{'character_id': 1, 'final_blow': True}],
            'victim': {'character_id': 3}
        }
        self.assertTrue(should_include_killmail(self.campaign, km_data))

    def test_should_include_killmail_global_no_match(self):
        # Friendly kills Random person outside of any specific location
        km_data = {
            'killmail_id': 20002,
            'killmail_time': timezone.now().isoformat(),
            'solar_system_id': 99999999,
            'attackers': [{'character_id': 1, 'final_blow': True}],
            'victim': {'character_id': 4}
        }
        self.assertFalse(should_include_killmail(self.campaign, km_data))

    def test_should_include_killmail_uses_db_cache(self):
        # Create an existing killmail in DB
        # Basic setup
        region = EveRegion.objects.create(id=10000002, name="Test Region 2")
        constellation = EveConstellation.objects.create(id=20000002, name="Test Const 2", eve_region=region)
        system = EveSolarSystem.objects.create(id=30000002, name="Test System 2", eve_constellation=constellation, security_status=0.5)
        char1 = EveCharacter.objects.get(character_id=1)

        campaign = Campaign.objects.create(
            name="Cache Test Campaign",
            start_date=timezone.now() - timezone.timedelta(days=1),
            is_active=True
        )
        campaign.systems.add(system)
        CampaignMember.objects.create(campaign=campaign, character=char1)

        CampaignKillmail.objects.create(
            campaign=campaign,
            killmail_id=99999,
            killmail_time=timezone.now(),
            solar_system=system,
            victim_id=2,
            victim_name="Victim",
            victim_corp_id=20,
            victim_corp_name="VCorp",
            total_value=1000
        )

        km_data = {
            'killmail_id': 99999,
            # No killmail_time or solar_system_id
            'attackers': [{'character_id': 1, 'final_blow': True}],
            'victim': {'character_id': 2}
        }

        # This should NOT call ESI and should return True because it's in the DB
        with patch('aacampaign.tasks._esi_session.get') as mock_get:
            self.assertTrue(should_include_killmail(campaign, km_data))
            mock_get.assert_not_called()
            self.assertIn('killmail_time', km_data)
            self.assertEqual(km_data['solar_system_id'], system.id)
