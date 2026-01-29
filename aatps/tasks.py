"""App Tasks"""

# Standard Library
import logging
import requests
import time
from calendar import monthrange
from datetime import datetime, timezone as dt_timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from celery import shared_task
from .models import MonthlyKillmail, KillmailParticipant
from .esi import esi, call_result
from allianceauth.eveonline.models import EveCharacter
from allianceauth.authentication.models import CharacterOwnership
from eveuniverse.models import EveSolarSystem, EveType
from django.db import transaction

logger = logging.getLogger(__name__)


# =============================================================================
# Data Collection Helpers
# =============================================================================

def get_all_auth_characters():
    """
    Return all characters owned by authenticated users.
    Returns a queryset of EveCharacter objects with their user relationships.
    """
    return EveCharacter.objects.filter(
        character_ownership__isnull=False
    ).select_related('character_ownership__user')


def get_current_month_range():
    """
    Return (start_datetime, end_datetime) for current month in UTC.
    """
    now = datetime.now(dt_timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, last_day = monthrange(now.year, now.month)
    end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def get_auth_character_ids():
    """
    Return a set of all character IDs owned by authenticated users.
    """
    return set(
        CharacterOwnership.objects.values_list('character__character_id', flat=True)
    )


def get_user_for_character(character_id):
    """
    Get the User associated with a character_id, or None if not found.
    """
    try:
        ownership = CharacterOwnership.objects.select_related('user').get(
            character__character_id=character_id
        )
        return ownership.user
    except CharacterOwnership.DoesNotExist:
        return None


# Reusable session for zKillboard calls
_zkill_session = requests.Session()
_zkill_retries = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504]
)
_zkill_session.mount('https://', HTTPAdapter(max_retries=_zkill_retries))

_last_zkill_call = 0


def _zkill_get(url):
    """
    Helper to perform GET requests to zKillboard with rate limiting.
    Enforces a minimum of 500ms between calls.
    """
    global _last_zkill_call
    now = time.time()
    elapsed = now - _last_zkill_call
    if elapsed < 0.5:
        sleep_time = 0.5 - elapsed
        time.sleep(sleep_time)

    contact_email = getattr(settings, 'ESI_USER_CONTACT_EMAIL', 'Unknown')
    headers = {
        'User-Agent': f'Alliance Auth TPS Plugin - Maintainer: {contact_email}',
        'Accept-Encoding': 'gzip',
    }

    logger.debug(f"Fetching from zKillboard: {url}")
    response = _zkill_session.get(url, headers=headers, timeout=30)
    _last_zkill_call = time.time()
    return response


def _fetch_universe_names(ids):
    try:
        data, _ = call_result(
            lambda: esi.client.Universe.PostUniverseNames,
            body=ids
        )
        return data
    except Exception:
        return None


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

    try:
        response = _zkill_get(url)
        data = response.json()
        if not isinstance(data, list):
            logger.error(
                f"Unexpected response from zKillboard for {entity_type} {entity_id}: "
                f"expected list, got {type(data)}. Content: {data}"
            )
            return None
        logger.debug(f"Fetched {len(data)} results from zKillboard for {entity_type} {entity_id}")
        return data
    except Exception as e:
        logger.error(f"Error fetching from zkillboard for {entity_type} {entity_id}: {e}")
        return None


def fetch_killmail_from_esi(killmail_id, killmail_hash):
    try:
        logger.debug(f"Fetching killmail {killmail_id} from ESI")
        data, _ = call_result(
            lambda: esi.client.Killmails.GetKillmailsKillmailIdKillmailHash,
            killmail_id=killmail_id,
            killmail_hash=killmail_hash
        )
        return data
    except Exception as e:
        logger.error(f"Error fetching killmail {killmail_id} from ESI: {e}")
        return None


def get_killmail_time(km_data):
    """Extract killmail time from km_data, handling various formats."""
    km_time_str = km_data.get('killmail_time')
    if km_time_str:
        try:
            km_time = timezone.datetime.fromisoformat(km_time_str.replace('Z', '+00:00'))
            if timezone.is_naive(km_time):
                km_time = timezone.make_aware(km_time)
            return km_time
        except Exception:
            pass

    # Try ESI if we have ID and Hash
    km_id = km_data.get('killmail_id')
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


# =============================================================================
# Monthly Killmail Data Collection
# =============================================================================

@shared_task(time_limit=7200)
def pull_monthly_killmails():
    """
    Pull killmails for all authenticated users for the current month.
    Runs hourly via Celery Beat.

    This task uses smart deduplication to minimize API calls:
    1. Pull by alliance first (covers all corps and chars in that alliance)
    2. Then pull by corp (for chars not in pulled alliances)
    3. Then pull individual chars only if needed
    """
    lock_id = "aatps-pull-monthly-killmails-lock"
    if not cache.add(lock_id, True, 7200):
        logger.warning("Monthly killmail pull task is already running. Skipping.")
        return "Task already running"

    try:
        return _pull_monthly_killmails_logic()
    finally:
        cache.delete(lock_id)


def _pull_monthly_killmails_logic():
    """Core logic for pulling monthly killmails."""
    logger.info("Monthly killmail pull task started")
    start_time = time.time()

    # Get current month range
    month_start, month_end = get_current_month_range()
    now = datetime.now(dt_timezone.utc)
    seconds_to_pull = int((now - month_start).total_seconds())

    logger.info(f"Pulling killmails for {month_start.strftime('%B %Y')} ({seconds_to_pull}s lookback)")

    # Get all auth characters and group them
    characters = get_all_auth_characters()

    # Build sets for deduplication
    alliances_to_pull = set()
    corps_to_pull = set()
    solo_characters = []

    # Track which corps belong to which alliances (for dedup)
    alliance_corp_map = {}  # alliance_id -> set of corp_ids

    for char in characters:
        if char.alliance_id:
            alliances_to_pull.add(char.alliance_id)
            alliance_corp_map.setdefault(char.alliance_id, set()).add(char.corporation_id)
        elif char.corporation_id:
            corps_to_pull.add(char.corporation_id)
        else:
            solo_characters.append(char.character_id)

    # Remove corps that are covered by alliance pulls
    corps_in_alliances = set()
    for corp_set in alliance_corp_map.values():
        corps_in_alliances.update(corp_set)
    corps_to_pull = corps_to_pull - corps_in_alliances

    logger.info(
        f"Entities to pull: {len(alliances_to_pull)} alliances, "
        f"{len(corps_to_pull)} corps, {len(solo_characters)} solo chars"
    )

    # Get all auth character IDs for participant matching
    auth_char_ids = get_auth_character_ids()

    # Local caches
    context = {
        'resolved_names': {},
        'resolved_characters': {},
        'resolved_systems': {},
        'resolved_types': {},
        'auth_char_ids': auth_char_ids,
    }

    processed_km_ids = set()
    total_killmails = 0
    total_participants = 0

    def process_page(kms):
        nonlocal total_killmails, total_participants
        new_kms = 0
        new_participants = 0

        for km_data in kms:
            km_id = km_data.get('killmail_id')
            if not km_id or km_id in processed_km_ids:
                continue

            processed_km_ids.add(km_id)

            # Check if killmail has any auth user involvement
            result = process_monthly_killmail(km_data, context, month_start)
            if result:
                new_kms += 1
                new_participants += result.get('participants', 0)

        total_killmails += new_kms
        total_participants += new_participants
        return new_kms

    # Pull alliances
    for i, alliance_id in enumerate(alliances_to_pull, 1):
        if time.time() - start_time > 7200:
            logger.warning("Task exceeded 2 hour limit, stopping early.")
            break

        logger.info(f"[Alliance {i}/{len(alliances_to_pull)}] Pulling alliance {alliance_id}")
        _pull_entity_killmails('allianceID', alliance_id, seconds_to_pull, month_start, process_page)

    # Pull corps not covered by alliances
    for i, corp_id in enumerate(corps_to_pull, 1):
        if time.time() - start_time > 7200:
            logger.warning("Task exceeded 2 hour limit, stopping early.")
            break

        logger.info(f"[Corp {i}/{len(corps_to_pull)}] Pulling corporation {corp_id}")
        _pull_entity_killmails('corporationID', corp_id, seconds_to_pull, month_start, process_page)

    # Pull solo characters
    for i, char_id in enumerate(solo_characters, 1):
        if time.time() - start_time > 7200:
            logger.warning("Task exceeded 2 hour limit, stopping early.")
            break

        logger.info(f"[Char {i}/{len(solo_characters)}] Pulling character {char_id}")
        _pull_entity_killmails('characterID', char_id, seconds_to_pull, month_start, process_page)

    elapsed = time.time() - start_time
    logger.info(
        f"Monthly killmail pull completed in {elapsed:.1f}s. "
        f"Processed {total_killmails} killmails, {total_participants} participants."
    )
    return f"Processed {total_killmails} killmails, {total_participants} participants"


def _pull_entity_killmails(entity_type, entity_id, seconds_to_pull, month_start, process_callback):
    """
    Pull killmails for a single entity and process them.
    Uses pastSeconds API for recent data.
    """
    page = 1
    max_pages = 50

    while page <= max_pages:
        kms = fetch_from_zkill(entity_type, entity_id, past_seconds=seconds_to_pull, page=page)
        if not kms:
            break

        logger.debug(f"Fetched page {page} ({len(kms)} kills) for {entity_type} {entity_id}")
        new_on_page = process_callback(kms)
        logger.debug(f"Processed {new_on_page} new killmails from page {page}")

        if len(kms) < 200:  # Last page
            break

        # Check if we've gone past the month start
        last_km_time = get_killmail_time(kms[-1])
        if last_km_time and last_km_time < month_start:
            break

        page += 1


def process_monthly_killmail(km_data, context, month_start):
    """
    Process a killmail for the new MonthlyKillmail model.
    Creates the killmail and links any auth user participants.

    Returns dict with 'participants' count if processed, None if skipped.
    """
    km_id = km_data.get('killmail_id')
    if not km_id:
        return None

    auth_char_ids = context.get('auth_char_ids', set())

    # Check if any auth user is involved (as attacker or victim)
    involved_auth_chars = []
    victim = km_data.get('victim', {})
    victim_char_id = victim.get('character_id')

    # Check victim
    victim_is_auth = victim_char_id and victim_char_id in auth_char_ids

    # Check attackers
    for attacker in km_data.get('attackers', []):
        char_id = attacker.get('character_id')
        if char_id and char_id in auth_char_ids:
            involved_auth_chars.append({
                'character_id': char_id,
                'is_victim': False,
                'is_final_blow': attacker.get('final_blow', False),
                'damage_done': attacker.get('damage_done', 0),
                'ship_type_id': attacker.get('ship_type_id', 0),
            })

    # Add victim if they're an auth user
    if victim_is_auth:
        involved_auth_chars.append({
            'character_id': victim_char_id,
            'is_victim': True,
            'is_final_blow': False,
            'damage_done': 0,
            'ship_type_id': victim.get('ship_type_id', 0),
        })

    if not involved_auth_chars:
        return None

    # Need full data - fetch from ESI if necessary
    needs_esi = any(k not in km_data for k in ['killmail_time', 'solar_system_id', 'victim', 'attackers'])
    if needs_esi:
        km_hash = km_data.get('zkb', {}).get('hash')
        if km_hash:
            esi_data = fetch_killmail_from_esi(km_id, km_hash)
            if esi_data:
                km_data.update(esi_data)
            else:
                logger.warning(f"Failed to fetch killmail {km_id} from ESI")
                return None
        else:
            logger.warning(f"Killmail {km_id} missing hash for ESI fetch")
            return None

    # Parse time
    try:
        km_time_str = km_data.get('killmail_time', '')
        km_time = timezone.datetime.fromisoformat(km_time_str.replace('Z', '+00:00'))
        if timezone.is_naive(km_time):
            km_time = timezone.make_aware(km_time)
    except (ValueError, TypeError) as e:
        logger.error(f"Killmail {km_id} has invalid time format: {e}")
        return None

    # Skip if before month start
    if km_time < month_start:
        return None

    # Resolve names and system info
    victim = km_data.get('victim', {})
    ship_type_id = victim.get('ship_type_id', 0)
    ship_type_name = "Unknown"
    ship_group_name = "Unknown"

    if ship_type_id:
        ship_type_name = _resolve_name(ship_type_id, context)
        try:
            s_type = context.get('resolved_types', {}).get(ship_type_id)
            if not s_type:
                s_type, _ = EveType.objects.get_or_create_esi(id=ship_type_id)
                context.setdefault('resolved_types', {})[ship_type_id] = s_type
            if s_type:
                if ship_type_name == "Unknown":
                    ship_type_name = getattr(s_type, "name", ship_type_name)
                if s_type.eve_group:
                    ship_group_name = s_type.eve_group.name
        except Exception as e:
            logger.warning(f"Failed to get ship group for {ship_type_id}: {e}")

    # Get system info
    system_id = km_data.get('solar_system_id', 0)
    system_name = "Unknown"
    region_id = None
    region_name = "Unknown"

    if system_id:
        system = context.get('resolved_systems', {}).get(system_id)
        if not system:
            try:
                system = EveSolarSystem.objects.select_related(
                    'eve_constellation__eve_region'
                ).get(id=system_id)
                context.setdefault('resolved_systems', {})[system_id] = system
            except EveSolarSystem.DoesNotExist:
                system = None

        if system:
            system_name = system.name
            if system.eve_constellation and system.eve_constellation.eve_region:
                region_id = system.eve_constellation.eve_region.id
                region_name = system.eve_constellation.eve_region.name

    # Resolve final blow attacker
    final_blow_attacker = next((a for a in km_data.get('attackers', []) if a.get('final_blow')), {})

    # Create or update the MonthlyKillmail
    with transaction.atomic():
        monthly_km, created = MonthlyKillmail.objects.update_or_create(
            killmail_id=km_id,
            defaults={
                'killmail_time': km_time,
                'solar_system_id': system_id,
                'solar_system_name': system_name,
                'region_id': region_id,
                'region_name': region_name,
                'ship_type_id': ship_type_id,
                'ship_type_name': ship_type_name,
                'ship_group_name': ship_group_name,
                'victim_id': victim.get('character_id', 0) or 0,
                'victim_name': _resolve_name(victim.get('character_id'), context) or "Unknown",
                'victim_corp_id': victim.get('corporation_id', 0) or 0,
                'victim_corp_name': _resolve_name(victim.get('corporation_id'), context) or "Unknown",
                'victim_alliance_id': victim.get('alliance_id'),
                'victim_alliance_name': _resolve_name(victim.get('alliance_id'), context) if victim.get('alliance_id') else None,
                'final_blow_char_id': final_blow_attacker.get('character_id', 0) or 0,
                'final_blow_char_name': _resolve_name(final_blow_attacker.get('character_id'), context) or "Unknown",
                'final_blow_corp_id': final_blow_attacker.get('corporation_id', 0) or 0,
                'final_blow_corp_name': _resolve_name(final_blow_attacker.get('corporation_id'), context) or "Unknown",
                'final_blow_alliance_id': final_blow_attacker.get('alliance_id'),
                'final_blow_alliance_name': _resolve_name(final_blow_attacker.get('alliance_id'), context) if final_blow_attacker.get('alliance_id') else None,
                'total_value': km_data.get('zkb', {}).get('totalValue', 0),
                'zkill_hash': km_data.get('zkb', {}).get('hash', ''),
            }
        )

        # Create participant records
        participants_created = 0
        for participant_data in involved_auth_chars:
            char_id = participant_data['character_id']

            # Get character object
            char = context.get('resolved_characters', {}).get(char_id)
            if not char:
                try:
                    char = EveCharacter.objects.get(character_id=char_id)
                except EveCharacter.DoesNotExist:
                    try:
                        char = EveCharacter.objects.create_character(char_id)
                    except Exception as e:
                        logger.warning(f"Failed to create EveCharacter for {char_id}: {e}")
                        continue
                context.setdefault('resolved_characters', {})[char_id] = char

            # Get user for character
            user = get_user_for_character(char_id)

            # Resolve ship name for participant
            participant_ship_id = participant_data.get('ship_type_id', 0)
            participant_ship_name = "Unknown"
            if participant_ship_id:
                participant_ship_name = _resolve_name(participant_ship_id, context) or "Unknown"

            # Create or update participant
            _, p_created = KillmailParticipant.objects.update_or_create(
                killmail=monthly_km,
                character=char,
                defaults={
                    'user': user,
                    'is_victim': participant_data['is_victim'],
                    'is_final_blow': participant_data['is_final_blow'],
                    'damage_done': participant_data['damage_done'],
                    'ship_type_id': participant_ship_id,
                    'ship_type_name': participant_ship_name,
                }
            )
            if p_created:
                participants_created += 1

    action = "Created" if created else "Updated"
    logger.debug(f"{action} MonthlyKillmail {km_id} with {participants_created} new participants")

    return {'participants': participants_created}


def _resolve_name(entity_id, context):
    """Helper to resolve entity name from cache or ESI."""
    if not entity_id:
        return None

    # Check cache first
    cached = context.get('resolved_names', {}).get(entity_id)
    if cached:
        return cached

    # Fetch from ESI
    data = _fetch_universe_names([entity_id])
    if data:
        name = data[0].get('name', 'Unknown')
        context.setdefault('resolved_names', {})[entity_id] = name
        return name

    return "Unknown"


@shared_task
def cleanup_old_killmails():
    """
    Remove killmails older than retention period.
    Runs daily via Celery Beat (recommended: 4:30 AM).

    The retention period is configured via AA_TPS_RETENTION_MONTHS setting.
    Default is 12 months.
    """
    from datetime import timedelta
    from .app_settings import AA_TPS_RETENTION_MONTHS

    cutoff = datetime.now(dt_timezone.utc) - timedelta(days=AA_TPS_RETENTION_MONTHS * 30)

    deleted_count, _ = MonthlyKillmail.objects.filter(
        killmail_time__lt=cutoff
    ).delete()

    logger.info(f"Cleaned up {deleted_count} MonthlyKillmail records older than {cutoff} "
                f"(retention: {AA_TPS_RETENTION_MONTHS} months)")
    return f"Deleted {deleted_count} old killmails"
