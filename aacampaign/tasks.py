"""App Tasks"""

# Standard Library
import logging
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.utils import timezone
from django.conf import settings
from celery import shared_task
from .models import Campaign, CampaignKillmail, CampaignMember, CampaignTarget
from allianceauth.eveonline.models import EveCharacter, EveCorporationInfo, EveAllianceInfo
from eveuniverse.models import EveSolarSystem, EveEntity, EveType
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)

# Reusable session for ESI calls with retry logic for 429/5xx errors
_esi_session = requests.Session()
_retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504]
)
_esi_session.mount('https://', HTTPAdapter(max_retries=_retries))

# Reusable session for zKillboard calls
_zkill_session = requests.Session()
_zkill_retries = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504]
)
_zkill_session.mount('https://', HTTPAdapter(max_retries=_zkill_retries))


def get_killmail_data_from_db(killmail_id):
    """
    Try to find killmail data in our database from previous campaign matches.
    Returns (killmail_time, solar_system_id) or (None, None)
    """
    existing = CampaignKillmail.objects.filter(killmail_id=killmail_id).first()
    if existing:
        return existing.killmail_time, existing.solar_system_id
    return None, None


@shared_task
def pull_zkillboard_data(past_seconds=None):
    """
    Pull data from ZKillboard for all active campaigns.
    Recommended to be scheduled hourly.
    """
    logger.info("ZKillboard data pull task started")
    now = timezone.now()
    twelve_hours_ago = now - timezone.timedelta(hours=12)
    active_campaigns = Campaign.objects.filter(
        is_active=True
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gt=twelve_hours_ago)
    ).prefetch_related('members', 'targets', 'systems', 'constellations', 'regions')

    if not active_campaigns.exists():
        logger.info("No active campaigns to process")
        return "No active campaigns"

    # Collect all unique entities to pull for and their required lookback
    entities = {} # (entity_type, entity_id) -> min_start_date
    for campaign in active_campaigns:
        def add_entity(etype, eid, start_date):
            if (etype, eid) not in entities or start_date < entities[(etype, eid)]:
                entities[(etype, eid)] = start_date

        # Pull for members
        for member in campaign.members.all():
            if member.character:
                add_entity('characterID', member.character.character_id, campaign.start_date)
            if member.corporation:
                add_entity('corporationID', member.corporation.corporation_id, campaign.start_date)
            if member.alliance:
                add_entity('allianceID', member.alliance.alliance_id, campaign.start_date)

        # Pull for targets
        for target in campaign.targets.all():
            if target.character:
                add_entity('characterID', target.character.character_id, campaign.start_date)
            if target.corporation:
                add_entity('corporationID', target.corporation.corporation_id, campaign.start_date)
            if target.alliance:
                add_entity('allianceID', target.alliance.alliance_id, campaign.start_date)

        # Pull for locations to catch all engagements in relevant areas
        for system in campaign.systems.all():
            add_entity('systemID', system.id, campaign.start_date)
        for constellation in campaign.constellations.all():
            add_entity('constellationID', constellation.id, campaign.start_date)
        for region in campaign.regions.all():
            add_entity('regionID', region.id, campaign.start_date)

    if not entities:
        logger.info(f"No entities found to pull for in {active_campaigns.count()} active campaigns")
        return "No entities found"

    logger.info(f"Pulling ZKillboard data for {len(entities)} unique entities across {active_campaigns.count()} campaigns")

    # Pull killmails for each entity and process them
    processed_ids = set()
    campaign_killmails_count = 0
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    total_entities = len(entities)
    for i, ((entity_type, entity_id), min_start_date) in enumerate(entities.items(), 1):
        if past_seconds:
            # If explicit past_seconds provided, it overrides the campaign start date
            min_start_date = timezone.now() - timezone.timedelta(seconds=past_seconds)
        else:
            # Default to pulling only today's data, but still respect campaign start date
            if min_start_date < today_start:
                min_start_date = today_start

        logger.info(f"[{i}/{total_entities}] Discovery for {entity_type} {entity_id} from {min_start_date}")

        reached_min_date = False
        curr_now = timezone.now()
        curr_year = curr_now.year
        curr_month = curr_now.month
        start_year = min_start_date.year
        start_month = min_start_date.month

        while (curr_year > start_year) or (curr_year == start_year and curr_month >= start_month):
            page = 1
            max_pages_per_month = 50
            logger.debug(f"Pulling {entity_type} {entity_id} for {curr_year}-{curr_month:02d}")

            while page <= max_pages_per_month:
                # Be polite to zKillboard
                if page > 1 or (curr_month != curr_now.month or curr_year != curr_now.year):
                    time.sleep(1)

                kms = fetch_from_zkill(entity_type, entity_id, page=page, year=curr_year, month=curr_month)
                if kms is None:
                    logger.error(f"Failed to fetch page {page} for {curr_year}-{curr_month:02d}. Skipping month.")
                    break

                if not kms:
                    logger.debug(f"No more killmails for {curr_year}-{curr_month:02d} at page {page}")
                    break

                logger.info(f"Fetched page {page} ({len(kms)} kills) for {entity_type} {entity_id} ({curr_year}-{curr_month:02d})")

                new_on_page = 0
                for km in kms:
                    km_id = km.get('killmail_id')
                    if km_id and km_id not in processed_ids:
                        processed_ids.add(km_id)

                        # Optimization: Identify campaigns that already have this killmail
                        # to avoid redundant ESI calls in should_include_killmail
                        existing_campaign_ids = set(CampaignKillmail.objects.filter(
                            killmail_id=km_id,
                            campaign__in=active_campaigns
                        ).values_list('campaign_id', flat=True))

                        campaigns_to_check = [c for c in active_campaigns if c.id not in existing_campaign_ids]

                        if not campaigns_to_check:
                            # We already have this killmail for all possible active campaigns
                            continue

                        new_on_page += 1
                        for campaign in campaigns_to_check:
                            if should_include_killmail(campaign, km):
                                process_killmail(campaign, km)
                                campaign_killmails_count += 1

                logger.info(f"Processed {new_on_page} unique killmails from page {page}")

                # Check if we should continue paging this month
                # Since results are usually desc, if the last km on page is older than min_start_date, we can stop
                last_km_time = get_killmail_time(kms[-1])
                if last_km_time and last_km_time < min_start_date:
                    reached_min_date = True
                    break

                page += 1

            if reached_min_date:
                logger.info(f"Reached data older than {min_start_date}. Stopping for {entity_type} {entity_id}.")
                break

            if page > max_pages_per_month:
                logger.warning(f"Reached max pages ({max_pages_per_month}) for {curr_year}-{curr_month:02d}. Moving to next month.")

            # Decrement month
            curr_month -= 1
            if curr_month < 1:
                curr_month = 12
                curr_year -= 1

    logger.info(f"Finished pulling ZKillboard data. Processed {campaign_killmails_count} campaign killmails. Task completed successfully.")
    return f"Processed {campaign_killmails_count} campaign killmails"

@shared_task
def repair_campaign_killmails():
    """
    Find killmails with missing ship information and attempt to repair them
    by fetching full data from zKillboard and ESI.
    """
    # Get unique killmail IDs that need repair
    kms_to_repair = CampaignKillmail.objects.filter(
        Q(ship_type_id=0) |
        Q(ship_group_name="Unknown") |
        Q(final_blow_char_id=0, final_blow_corp_id=0) |
        Q(final_blow_char_name="", final_blow_char_id__gt=0) |
        Q(final_blow_corp_name="Unknown", final_blow_corp_id__gt=0)
    ).values_list('killmail_id', flat=True).distinct()
    if not kms_to_repair:
        logger.info("No killmails found in need of repair")
        return "No killmails to repair"

    total = len(kms_to_repair)
    logger.info(f"Repairing {total} killmails with missing information")

    repaired_count = 0
    for km_id in kms_to_repair:
        if repair_killmail_by_id(km_id):
            repaired_count += 1
            if repaired_count % 10 == 0:
                logger.info(f"Repaired {repaired_count}/{total} killmails")

    logger.info(f"Finished repair. Successfully repaired {repaired_count} killmails.")
    return f"Repaired {repaired_count} killmails"

def repair_killmail_by_id(km_id):
    """
    Finds a killmail on zKillboard and processes it for all relevant campaigns.
    Returns True if found and processed, False otherwise.
    """
    url = f"https://zkillboard.com/api/killID/{km_id}/"
    contact_email = getattr(settings, 'ESI_USER_CONTACT_EMAIL', 'Unknown')
    headers = {
        'User-Agent': f'Alliance Auth Campaign Plugin Repair - Maintainer: {contact_email}',
        'Accept-Encoding': 'gzip',
    }
    try:
        time.sleep(1) # Be polite
        response = _zkill_session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            km_data = data[0]
            # should_include_killmail will fetch from ESI because it's missing 'victim'
            # but it needs a campaign. We iterate over all campaigns this killmail belongs to.
            campaigns = Campaign.objects.filter(killmails__killmail_id=km_id).distinct()
            repaired = False
            for campaign in campaigns:
                if should_include_killmail(campaign, km_data):
                    process_killmail(campaign, km_data)
                    repaired = True
                else:
                    logger.debug(f"Killmail {km_id} does not match campaign {campaign} anymore during repair")
            return repaired
        else:
            logger.warning(f"Could not find killmail {km_id} on zKillboard for repair")
    except Exception as e:
        logger.error(f"Error repairing killmail {km_id}: {e}")
    return False

def fetch_from_zkill(entity_type, entity_id, past_seconds=None, page=None, year=None, month=None):
    if past_seconds:
        url = f"https://zkillboard.com/api/{entity_type}/{entity_id}/pastSeconds/{past_seconds}/"
    else:
        url = f"https://zkillboard.com/api/{entity_type}/{entity_id}/"
        if year and month:
            url += f"year/{year}/month/{month}/"
        if page:
            url += f"page/{page}/"
        else:
            url += "page/1/"

    contact_email = getattr(settings, 'ESI_USER_CONTACT_EMAIL', 'Unknown')
    headers = {
        'User-Agent': f'Alliance Auth Campaign Plugin - Maintainer: {contact_email}',
        'Accept-Encoding': 'gzip',
    }
    try:
        logger.debug(f"Fetching from zKillboard: {url}")
        response = _zkill_session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            logger.error(
                f"Unexpected response from zKillboard for {entity_type} {entity_id}: "
                f"expected list, got {type(data)}. Content: {data}"
            )
            return None
        return data
    except Exception as e:
        logger.error(f"Error fetching from zkillboard for {entity_type} {entity_id}: {e}")
        return None

def fetch_killmail_from_esi(killmail_id, killmail_hash):
    url = f"https://esi.evetech.net/latest/killmails/{killmail_id}/{killmail_hash}/?datasource=tranquility"
    contact_email = getattr(settings, 'ESI_USER_CONTACT_EMAIL', 'Unknown')
    headers = {
        'User-Agent': f'Alliance Auth Campaign Plugin - Maintainer: {contact_email}',
    }
    try:
        # Be polite to ESI, especially during historical pulls
        time.sleep(0.05)
        logger.debug(f"Fetching killmail {killmail_id} from ESI")
        response = _esi_session.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching killmail {killmail_id} from ESI: {e}")
        return None

def get_killmail_time(km_data):
    # Try to get it from km_data
    km_time_str = km_data.get('killmail_time')
    if km_time_str:
        try:
            km_time = timezone.datetime.fromisoformat(km_time_str.replace('Z', '+00:00'))
            if timezone.is_naive(km_time):
                km_time = timezone.make_aware(km_time)
            return km_time
        except Exception:
            pass

    # Not found, try local DB first
    km_id = km_data.get('killmail_id')
    if km_id:
        db_time, _ = get_killmail_data_from_db(km_id)
        if db_time:
            return db_time

    # Not found in DB, try ESI if we have ID and Hash
    km_hash = km_data.get('zkb', {}).get('hash')
    if km_id and km_hash:
        esi_data = fetch_killmail_from_esi(km_id, km_hash)
        if esi_data:
            km_time_str = esi_data.get('killmail_time')
            if km_time_str:
                try:
                    km_time = timezone.datetime.fromisoformat(km_time_str.replace('Z', '+00:00'))
                    if timezone.is_naive(km_time):
                        km_time = timezone.make_aware(km_time)
                    return km_time
                except Exception:
                    pass
    return None

def should_include_killmail(campaign, km_data):
    # Basic validation
    km_id = km_data.get('killmail_id', 'Unknown')

    # Check if we have enough data to evaluate involvement and process it correctly
    # We need: time, system, victim (for ship info), and attackers (for involvement and final blow)
    has_full_attackers = 'attackers' in km_data and any('final_blow' in a for a in km_data['attackers'])
    needs_esi = any(k not in km_data for k in ['killmail_time', 'solar_system_id', 'victim', 'attackers']) or not has_full_attackers

    if needs_esi:
        km_id_val = km_data.get('killmail_id')
        km_hash = km_data.get('zkb', {}).get('hash')

        # Check local DB cache for time/system/victim if that's all we were missing
        # But if we are missing attackers with final blow info, we usually need ESI
        if ('killmail_time' not in km_data or 'solar_system_id' not in km_data):
            if km_id_val:
                db_time, db_system_id = get_killmail_data_from_db(km_id_val)
                if db_time and db_system_id:
                    km_data['killmail_time'] = db_time.isoformat()
                    km_data['solar_system_id'] = db_system_id
                    # Re-check if we still need ESI
                    has_full_attackers = 'attackers' in km_data and any('final_blow' in a for a in km_data['attackers'])
                    needs_esi = any(k not in km_data for k in ['killmail_time', 'solar_system_id', 'victim', 'attackers']) or not has_full_attackers

        if needs_esi:
            if km_hash:
                logger.info(f"Killmail {km_id} missing full data (ESI fetch needed={needs_esi}, has_full_attackers={has_full_attackers}), attempting to fetch from ESI")
                esi_data = fetch_killmail_from_esi(km_id_val, km_hash)
                if esi_data:
                    km_data.update(esi_data)
                else:
                    logger.warning(f"Killmail {km_id} missing required fields and ESI fetch failed")
                    return False
            else:
                logger.warning(f"Killmail {km_id} missing required fields and no hash available for ESI fetch")
                return False

    # Time check
    try:
        km_time = timezone.datetime.fromisoformat(km_data['killmail_time'].replace('Z', '+00:00'))
        if timezone.is_naive(km_time):
            km_time = timezone.make_aware(km_time)
    except (ValueError, TypeError) as e:
        logger.error(f"Killmail {km_id} has invalid time format: {km_data.get('killmail_time')} - {e}")
        return False

    if km_time < campaign.start_date:
        logger.debug(f"Killmail {km_id} skipped for campaign {campaign}: before campaign start ({km_time} < {campaign.start_date})")
        return False
    if campaign.end_date and km_time > campaign.end_date:
        logger.debug(f"Killmail {km_id} skipped for campaign {campaign}: after campaign end")
        return False

    # Involvement check
    friendly_ids = get_campaign_friendly_ids(campaign)
    friendly_involved = is_entity_involved(km_data, friendly_ids)

    if not friendly_involved:
        logger.debug(f"Killmail {km_id} skipped for campaign {campaign}: no friendly involvement")
        return False

    # Target check
    target_ids = get_campaign_target_ids(campaign)
    has_targets = any(target_ids.values())
    target_involved = is_entity_involved(km_data, target_ids)

    if target_involved:
        logger.info(f"Killmail {km_id} matched for campaign {campaign}: target involved")
        return True

    # Check if campaign is location restricted
    has_locations = (
        campaign.systems.exists() or
        campaign.regions.exists() or
        campaign.constellations.exists()
    )

    if not has_locations:
        if not has_targets:
            # Global campaign with no specific targets -> match everything involving friendly
            logger.info(f"Killmail {km_id} matched for campaign {campaign}: global campaign (no targets/locations)")
            return True
        else:
            # Global campaign with targets -> must match a target (already checked above)
            logger.debug(f"Killmail {km_id} skipped for campaign {campaign}: global campaign, but no target match")
            return False

    # Location check
    system_id = km_data.get('solar_system_id')
    if not system_id:
        logger.warning(f"Killmail {km_id} missing solar_system_id even after ESI fetch/DB lookup")
        return False

    location_match = False
    try:
        system = EveSolarSystem.objects.get(id=system_id)
    except EveSolarSystem.DoesNotExist:
        system = None

    if campaign.systems.filter(id=system_id).exists():
        location_match = True
    elif system:
        if campaign.regions.filter(id=system.eve_constellation.eve_region_id).exists():
            location_match = True
        elif campaign.constellations.filter(id=system.eve_constellation_id).exists():
            location_match = True

    if location_match:
        logger.info(f"Killmail {km_id} matched for campaign {campaign}: location match")
        return True

    logger.debug(f"Killmail {km_id} skipped for campaign {campaign}: no target or location match")
    return False

def get_campaign_friendly_ids(campaign):
    # Cache this maybe?
    ids = {'characters': set(), 'corporations': set(), 'alliances': set()}
    for member in campaign.members.all():
        if member.character:
            ids['characters'].add(member.character.character_id)
        if member.corporation:
            ids['corporations'].add(member.corporation.corporation_id)
        if member.alliance:
            ids['alliances'].add(member.alliance.alliance_id)
    return ids

def get_campaign_target_ids(campaign):
    ids = {'characters': set(), 'corporations': set(), 'alliances': set()}
    for target in campaign.targets.all():
        if target.character:
            ids['characters'].add(target.character.character_id)
        if target.corporation:
            ids['corporations'].add(target.corporation.corporation_id)
        if target.alliance:
            ids['alliances'].add(target.alliance.alliance_id)
    return ids

def is_entity_involved(km_data, entity_ids):
    # Check attackers
    for attacker in km_data.get('attackers', []):
        if attacker.get('character_id') in entity_ids['characters']:
            return True
        if attacker.get('corporation_id') in entity_ids['corporations']:
            return True
        if attacker.get('alliance_id') in entity_ids['alliances']:
            return True

    # Check victim
    victim = km_data.get('victim', {})
    if victim.get('character_id') in entity_ids['characters']:
        return True
    if victim.get('corporation_id') in entity_ids['corporations']:
        return True
    if victim.get('alliance_id') in entity_ids['alliances']:
        return True

    return False

def process_killmail(campaign, km_data):
    km_id = km_data['killmail_id']
    try:
        km_time = timezone.datetime.fromisoformat(km_data['killmail_time'].replace('Z', '+00:00'))
        if timezone.is_naive(km_time):
            km_time = timezone.make_aware(km_time)
    except (KeyError, ValueError, TypeError):
        logger.error(f"Failed to parse killmail_time for killmail {km_id}")
        return

    # Is it a loss for our side?
    friendly_ids = get_campaign_friendly_ids(campaign)
    victim = km_data.get('victim', {})
    is_loss = False
    if (victim.get('character_id') in friendly_ids['characters'] or
        victim.get('corporation_id') in friendly_ids['corporations'] or
        victim.get('alliance_id') in friendly_ids['alliances']):
        is_loss = True

    # Resolve names
    victim_id = victim.get('character_id', 0)
    victim_corp_id = victim.get('corporation_id', 0)
    victim_alliance_id = victim.get('alliance_id')

    ship_type_id = victim.get('ship_type_id', 0)
    ship_type_name = "Unknown"
    ship_group_name = "Unknown"
    if ship_type_id:
        s_entity, _ = EveEntity.objects.get_or_create_esi(id=ship_type_id)
        ship_type_name = s_entity.name
        try:
            # Also get ship group name for stats
            s_type, _ = EveType.objects.get_or_create_esi(id=ship_type_id)
            if s_type and s_type.eve_group:
                ship_group_name = s_type.eve_group.name
        except Exception as e:
            logger.warning(f"Failed to get ship group for {ship_type_id}: {e}")

    victim_name = "Unknown"
    if victim_id:
        v_entity, _ = EveEntity.objects.get_or_create_esi(id=victim_id)
        victim_name = v_entity.name

    victim_corp_name = "Unknown"
    if victim_corp_id:
        c_entity, _ = EveEntity.objects.get_or_create_esi(id=victim_corp_id)
        victim_corp_name = c_entity.name

    victim_alliance_name = ""
    if victim_alliance_id:
        a_entity, _ = EveEntity.objects.get_or_create_esi(id=victim_alliance_id)
        victim_alliance_name = a_entity.name

    # Resolve Final Blow attacker
    final_blow_attacker = next((a for a in km_data.get('attackers', []) if a.get('final_blow')), {})
    if not final_blow_attacker:
        logger.warning(f"Killmail {km_id} has no attacker marked as final blow. Attackers count: {len(km_data.get('attackers', []))}")

    fb_char_id = final_blow_attacker.get('character_id', 0)
    fb_corp_id = final_blow_attacker.get('corporation_id', 0)
    fb_alliance_id = final_blow_attacker.get('alliance_id')

    fb_char_name = ""
    if fb_char_id:
        fb_c_entity, _ = EveEntity.objects.get_or_create_esi(id=fb_char_id)
        fb_char_name = fb_c_entity.name

    fb_corp_name = "Unknown"
    if fb_corp_id:
        fb_corp_entity, _ = EveEntity.objects.get_or_create_esi(id=fb_corp_id)
        fb_corp_name = fb_corp_entity.name

    fb_alliance_name = ""
    if fb_alliance_id:
        fb_a_entity, _ = EveEntity.objects.get_or_create_esi(id=fb_alliance_id)
        fb_alliance_name = fb_a_entity.name

    # Get system
    try:
        system = EveSolarSystem.objects.get(id=km_data['solar_system_id'])
    except EveSolarSystem.DoesNotExist:
        system = None

    with transaction.atomic():
        ckm, created = CampaignKillmail.objects.update_or_create(
            campaign=campaign,
            killmail_id=km_id,
            defaults={
                'killmail_time': km_time,
                'solar_system': system,
                'ship_type_id': ship_type_id,
                'ship_type_name': ship_type_name,
                'ship_group_name': ship_group_name,
                'victim_id': victim_id,
                'victim_name': victim_name,
                'victim_corp_id': victim_corp_id,
                'victim_corp_name': victim_corp_name,
                'victim_alliance_id': victim_alliance_id,
                'victim_alliance_name': victim_alliance_name,
                'final_blow_char_id': fb_char_id,
                'final_blow_char_name': fb_char_name,
                'final_blow_corp_id': fb_corp_id,
                'final_blow_corp_name': fb_corp_name,
                'final_blow_alliance_id': fb_alliance_id,
                'final_blow_alliance_name': fb_alliance_name,
                'total_value': km_data.get('zkb', {}).get('totalValue', 0),
                'is_loss': is_loss,
            }
        )

        # Update attackers
        friendly_attackers = []
        for attacker in km_data.get('attackers', []):
            char_id = attacker.get('character_id')
            corp_id = attacker.get('corporation_id')
            alliance_id = attacker.get('alliance_id')

            is_friendly = (
                (char_id and char_id in friendly_ids['characters']) or
                (corp_id and corp_id in friendly_ids['corporations']) or
                (alliance_id and alliance_id in friendly_ids['alliances'])
            )

            if is_friendly and char_id:
                try:
                    char = EveCharacter.objects.get(character_id=char_id)
                except EveCharacter.DoesNotExist:
                    try:
                        # create_character fetches from ESI and creates the object
                        char = EveCharacter.objects.create_character(char_id)
                    except Exception as e:
                        logger.warning(f"Failed to create EveCharacter for {char_id}: {e}")
                        continue
                friendly_attackers.append(char)
            # What if the character is in a friendly corp/alliance but not in our DB?
            # We can only track characters we have in our DB for the leaderboard

        if friendly_attackers:
            ckm.attackers.set(friendly_attackers)
