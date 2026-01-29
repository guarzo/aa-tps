"""App Views"""

from calendar import monthrange
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth.decorators import login_required, permission_required
from django.core.handlers.wsgi import WSGIRequest
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDay
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render

from allianceauth.eveonline.models import EveCharacter

from .models import MonthlyKillmail, KillmailParticipant


def get_current_month_range():
    """Return (start_datetime, end_datetime) for current month in UTC."""
    now = datetime.now(dt_timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, last_day = monthrange(now.year, now.month)
    end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def get_month_range(year, month):
    """Return (start_datetime, end_datetime) for a specific month in UTC."""
    start = datetime(year, month, 1, 0, 0, 0, 0, tzinfo=dt_timezone.utc)
    _, last_day = monthrange(year, month)
    end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=dt_timezone.utc)
    return start, end


def get_month_params_from_request(request):
    """
    Extract year/month from request GET params.
    Returns (start, end, year, month, is_current).
    """
    now = datetime.now(dt_timezone.utc)
    year = request.GET.get('year')
    month = request.GET.get('month')

    if year and month:
        try:
            year = int(year)
            month = int(month)
            if month < 1 or month > 12:
                raise ValueError("Invalid month")
            start, end = get_month_range(year, month)
            is_current = (year == now.year and month == now.month)
            return start, end, year, month, is_current
        except (ValueError, TypeError):
            pass

    # Default to current month
    start, end = get_current_month_range()
    return start, end, now.year, now.month, True


def format_isk(value):
    """Format ISK value for display."""
    if value is None:
        return "0"
    value = float(value)
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    elif value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.0f}"


@login_required
@permission_required("aatps.basic_access")
def dashboard(request: WSGIRequest) -> HttpResponse:
    """Main dashboard showing current month activity."""
    month_start, month_end = get_current_month_range()
    now = datetime.now(dt_timezone.utc)

    # Get current user's characters
    user_chars = EveCharacter.objects.filter(
        character_ownership__user=request.user
    )

    context = {
        "month_name": month_start.strftime("%B %Y"),
        "year": now.year,
        "month": now.month,
        "month_start": month_start,
        "month_end": month_end,
        "user_characters": user_chars,
        "is_current_month": True,
    }
    return render(request, "aatps/dashboard.html", context)


@login_required
@permission_required("aatps.basic_access")
def historical_view(request: WSGIRequest, year: int, month: int) -> HttpResponse:
    """View historical data for a specific month."""
    now = datetime.now(dt_timezone.utc)

    # Validate month
    if month < 1 or month > 12:
        raise Http404("Invalid month")

    try:
        target_date = datetime(year, month, 1, tzinfo=dt_timezone.utc)
    except ValueError:
        raise Http404("Invalid date")

    # Don't allow future months
    if target_date > now:
        raise Http404("Cannot view future data")

    # Calculate date range for the requested month
    month_start, month_end = get_month_range(year, month)

    # Get current user's characters
    user_chars = EveCharacter.objects.filter(
        character_ownership__user=request.user
    )

    context = {
        "month_name": target_date.strftime("%B %Y"),
        "year": year,
        "month": month,
        "month_start": month_start,
        "month_end": month_end,
        "user_characters": user_chars,
        "is_current_month": (year == now.year and month == now.month),
    }
    return render(request, "aatps/dashboard.html", context)


@login_required
@permission_required("aatps.basic_access")
def stats_api(request: WSGIRequest) -> JsonResponse:
    """Return overall statistics for the dashboard."""
    month_start, month_end, year, month, is_current = get_month_params_from_request(request)

    # Get all killmails for the month
    killmails = MonthlyKillmail.objects.filter(
        killmail_time__gte=month_start,
        killmail_time__lte=month_end,
    )

    # Get participants to determine kills vs losses
    participants = KillmailParticipant.objects.filter(
        killmail__killmail_time__gte=month_start,
        killmail__killmail_time__lte=month_end,
    )

    # Kills: killmails where we have non-victim participants
    kill_km_ids = participants.filter(
        is_victim=False
    ).values_list('killmail_id', flat=True).distinct()

    # Losses: killmails where we have victim participants
    loss_km_ids = participants.filter(
        is_victim=True
    ).values_list('killmail_id', flat=True).distinct()

    # Get aggregates for kills
    kills_qs = killmails.filter(killmail_id__in=kill_km_ids)
    kills_stats = kills_qs.aggregate(
        total_kills=Count('killmail_id'),
        total_kill_value=Sum('total_value')
    )

    # Get aggregates for losses
    losses_qs = killmails.filter(killmail_id__in=loss_km_ids)
    losses_stats = losses_qs.aggregate(
        total_losses=Count('killmail_id'),
        total_loss_value=Sum('total_value')
    )

    total_kills = kills_stats['total_kills'] or 0
    total_kill_value = kills_stats['total_kill_value'] or 0
    total_losses = losses_stats['total_losses'] or 0
    total_loss_value = losses_stats['total_loss_value'] or 0

    # Calculate efficiency
    if total_kill_value and total_loss_value:
        efficiency = float(total_kill_value) / (float(total_kill_value) + float(total_loss_value)) * 100
    elif total_kill_value:
        efficiency = 100.0
    else:
        efficiency = 0.0

    # Count active pilots (unique users with participation)
    active_pilots = participants.filter(
        user__isnull=False
    ).values('user').distinct().count()

    return JsonResponse({
        'total_kills': total_kills,
        'total_losses': total_losses,
        'total_kill_value': float(total_kill_value),
        'total_loss_value': float(total_loss_value),
        'total_kill_value_formatted': format_isk(total_kill_value),
        'total_loss_value_formatted': format_isk(total_loss_value),
        'efficiency': round(efficiency, 1),
        'active_pilots': active_pilots,
        'year': year,
        'month': month,
    })


@login_required
@permission_required("aatps.basic_access")
def activity_api(request: WSGIRequest) -> JsonResponse:
    """Returns daily activity data for charts."""
    month_start, month_end, year, month, is_current = get_month_params_from_request(request)

    # Get participants for the month
    participants = KillmailParticipant.objects.filter(
        killmail__killmail_time__gte=month_start,
        killmail__killmail_time__lte=month_end,
    ).select_related('killmail')

    # Get kill killmail IDs (non-victim participants)
    kill_km_ids = set(
        participants.filter(is_victim=False)
        .values_list('killmail_id', flat=True)
        .distinct()
    )

    # Get loss killmail IDs (victim participants)
    loss_km_ids = set(
        participants.filter(is_victim=True)
        .values_list('killmail_id', flat=True)
        .distinct()
    )

    # Get daily kills
    daily_kills = (
        MonthlyKillmail.objects
        .filter(
            killmail_time__gte=month_start,
            killmail_time__lte=month_end,
            killmail_id__in=kill_km_ids
        )
        .annotate(day=TruncDay('killmail_time'))
        .values('day')
        .annotate(
            kills=Count('killmail_id'),
            kill_value=Sum('total_value')
        )
        .order_by('day')
    )

    # Get daily losses
    daily_losses = (
        MonthlyKillmail.objects
        .filter(
            killmail_time__gte=month_start,
            killmail_time__lte=month_end,
            killmail_id__in=loss_km_ids
        )
        .annotate(day=TruncDay('killmail_time'))
        .values('day')
        .annotate(
            losses=Count('killmail_id'),
            loss_value=Sum('total_value')
        )
        .order_by('day')
    )

    # Combine into a single structure keyed by day
    data = {}
    for row in daily_kills:
        day_str = row['day'].strftime('%Y-%m-%d')
        data[day_str] = {
            'day': day_str,
            'kills': row['kills'],
            'losses': 0,
            'kill_value': float(row['kill_value'] or 0),
            'loss_value': 0,
        }

    for row in daily_losses:
        day_str = row['day'].strftime('%Y-%m-%d')
        if day_str in data:
            data[day_str]['losses'] = row['losses']
            data[day_str]['loss_value'] = float(row['loss_value'] or 0)
        else:
            data[day_str] = {
                'day': day_str,
                'kills': 0,
                'losses': row['losses'],
                'kill_value': 0,
                'loss_value': float(row['loss_value'] or 0),
            }

    # Sort by day and return as list
    sorted_data = sorted(data.values(), key=lambda x: x['day'])

    return JsonResponse({'data': sorted_data})


@login_required
@permission_required("aatps.basic_access")
def leaderboard_api(request: WSGIRequest) -> JsonResponse:
    """Server-side DataTables API for leaderboard."""
    month_start, month_end, year, month, is_current = get_month_params_from_request(request)

    # DataTables parameters
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 10))
    search_value = request.GET.get('search[value]', '').lower()

    # Get all non-victim participations for the month
    participations = KillmailParticipant.objects.filter(
        killmail__killmail_time__gte=month_start,
        killmail__killmail_time__lte=month_end,
        is_victim=False,
    ).select_related('killmail', 'user', 'character')

    # Group by user (or character if no user)
    # We need to aggregate kills and values, deduplicating when multiple
    # characters from the same user are on the same killmail
    groups = {}

    for p in participations:
        km_id = p.killmail_id
        val = float(p.killmail.total_value)

        if p.user:
            key = ('U', p.user.id)
            # Get main character name
            try:
                main_char = p.user.profile.main_character
                display_name = main_char.character_name if main_char else p.character.character_name
                portrait_id = main_char.character_id if main_char else p.character.character_id
            except Exception:
                display_name = p.character.character_name
                portrait_id = p.character.character_id
        else:
            key = ('C', p.character.character_id)
            display_name = p.character.character_name
            portrait_id = p.character.character_id

        if key not in groups:
            groups[key] = {
                'character_name': display_name,
                'portrait_id': portrait_id,
                'kills_set': set(),
                'kill_value': 0.0,
                'final_blows': 0,
            }

        # Only count each killmail once per user
        if km_id not in groups[key]['kills_set']:
            groups[key]['kills_set'].add(km_id)
            groups[key]['kill_value'] += val

        if p.is_final_blow:
            groups[key]['final_blows'] += 1

    # Convert to list
    data_list = []
    for key, stats in groups.items():
        stats['group_key'] = key
        stats['kills'] = len(stats.pop('kills_set'))
        data_list.append(stats)

    # Calculate total records before filtering
    records_total = len(data_list)

    # Filtering (search)
    if search_value:
        data_list = [
            d for d in data_list
            if search_value in d['character_name'].lower()
        ]

    records_filtered = len(data_list)

    # Sorting
    order_column_index = request.GET.get('order[0][column]')
    order_dir = request.GET.get('order[0][dir]', 'desc')

    sort_columns = {
        '0': 'character_name',
        '1': 'kills',
        '2': 'final_blows',
        '3': 'kill_value',
    }
    sort_field = sort_columns.get(order_column_index, 'kill_value')
    data_list.sort(key=lambda x: x.get(sort_field, 0), reverse=(order_dir == 'desc'))

    # Paging
    paged_data = data_list[start:start + length]

    # Add rank and format values
    for i, entry in enumerate(paged_data):
        entry.pop('group_key', None)
        global_index = start + i
        entry['rank'] = global_index + 1
        entry['kill_value_formatted'] = format_isk(entry['kill_value'])

    return JsonResponse({
        'draw': draw,
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': paged_data,
    })


@login_required
@permission_required("aatps.basic_access")
def top_kills_api(request: WSGIRequest) -> JsonResponse:
    """Returns top kills for the month."""
    month_start, month_end, year, month, is_current = get_month_params_from_request(request)
    limit = int(request.GET.get('limit', 10))

    # Get kill killmail IDs (killmails with non-victim participants)
    kill_km_ids = KillmailParticipant.objects.filter(
        killmail__killmail_time__gte=month_start,
        killmail__killmail_time__lte=month_end,
        is_victim=False,
    ).values_list('killmail_id', flat=True).distinct()

    # Get top kills by value
    top_kills = MonthlyKillmail.objects.filter(
        killmail_time__gte=month_start,
        killmail_time__lte=month_end,
        killmail_id__in=kill_km_ids,
    ).order_by('-total_value')[:limit]

    data = []
    for km in top_kills:
        data.append({
            'killmail_id': km.killmail_id,
            'ship_type_id': km.ship_type_id,
            'ship_type_name': km.ship_type_name,
            'victim_name': km.victim_name,
            'victim_corp_name': km.victim_corp_name,
            'total_value': float(km.total_value),
            'total_value_formatted': format_isk(km.total_value),
            'killmail_time': km.killmail_time.isoformat(),
            'solar_system_name': km.solar_system_name,
        })

    return JsonResponse({'data': data})


@login_required
@permission_required("aatps.basic_access")
def ship_stats_api(request: WSGIRequest) -> JsonResponse:
    """Returns ship class statistics for the month."""
    month_start, month_end, year, month, is_current = get_month_params_from_request(request)

    # Get participants for the month
    participants = KillmailParticipant.objects.filter(
        killmail__killmail_time__gte=month_start,
        killmail__killmail_time__lte=month_end,
    )

    # Get kill and loss killmail IDs
    kill_km_ids = set(
        participants.filter(is_victim=False)
        .values_list('killmail_id', flat=True)
        .distinct()
    )
    loss_km_ids = set(
        participants.filter(is_victim=True)
        .values_list('killmail_id', flat=True)
        .distinct()
    )

    # Get ship group stats for kills
    kill_stats = (
        MonthlyKillmail.objects
        .filter(
            killmail_time__gte=month_start,
            killmail_time__lte=month_end,
            killmail_id__in=kill_km_ids
        )
        .values('ship_group_name')
        .annotate(count=Count('killmail_id'))
        .order_by('-count')
    )

    # Get ship group stats for losses
    loss_stats = (
        MonthlyKillmail.objects
        .filter(
            killmail_time__gte=month_start,
            killmail_time__lte=month_end,
            killmail_id__in=loss_km_ids
        )
        .values('ship_group_name')
        .annotate(count=Count('killmail_id'))
        .order_by('-count')
    )

    # Combine into a single structure
    ship_stats = {}
    for row in kill_stats:
        group = row['ship_group_name'] or "Unknown"
        if group not in ship_stats:
            ship_stats[group] = {'killed': 0, 'lost': 0}
        ship_stats[group]['killed'] += row['count']

    for row in loss_stats:
        group = row['ship_group_name'] or "Unknown"
        if group not in ship_stats:
            ship_stats[group] = {'killed': 0, 'lost': 0}
        ship_stats[group]['lost'] += row['count']

    # Convert to list format for charts
    data = [
        {
            'ship_group': group,
            'killed': stats['killed'],
            'lost': stats['lost'],
        }
        for group, stats in sorted(ship_stats.items(), key=lambda x: x[1]['killed'], reverse=True)
    ]

    return JsonResponse({'data': data})


@login_required
@permission_required("aatps.basic_access")
def my_stats_api(request: WSGIRequest) -> JsonResponse:
    """Return personal statistics for the current user."""
    month_start, month_end, year, month, is_current = get_month_params_from_request(request)

    # Get user's character IDs
    user_char_ids = list(
        EveCharacter.objects.filter(
            character_ownership__user=request.user
        ).values_list('character_id', flat=True)
    )

    if not user_char_ids:
        return JsonResponse({
            'kills': 0,
            'losses': 0,
            'kill_value': 0,
            'loss_value': 0,
            'kill_value_formatted': '0',
            'loss_value_formatted': '0',
            'final_blows': 0,
            'efficiency': 0,
            'rank': None,
            'favorite_ship': None,
        })

    # Get user's participations
    participations = KillmailParticipant.objects.filter(
        character__character_id__in=user_char_ids,
        killmail__killmail_time__gte=month_start,
        killmail__killmail_time__lte=month_end,
    ).select_related('killmail')

    # Calculate kills (unique killmails where user is attacker)
    kill_kms = set()
    kill_value = Decimal('0')
    final_blows = 0
    ship_counts = {}

    for p in participations.filter(is_victim=False):
        if p.killmail_id not in kill_kms:
            kill_kms.add(p.killmail_id)
            kill_value += p.killmail.total_value
        if p.is_final_blow:
            final_blows += 1
        # Track ships used
        if p.ship_type_name and p.ship_type_name != "Unknown":
            ship_counts[p.ship_type_name] = ship_counts.get(p.ship_type_name, 0) + 1

    # Calculate losses (unique killmails where user is victim)
    loss_kms = set()
    loss_value = Decimal('0')

    for p in participations.filter(is_victim=True):
        if p.killmail_id not in loss_kms:
            loss_kms.add(p.killmail_id)
            loss_value += p.killmail.total_value

    kills = len(kill_kms)
    losses = len(loss_kms)

    # Calculate efficiency
    if kill_value and loss_value:
        efficiency = float(kill_value) / (float(kill_value) + float(loss_value)) * 100
    elif kill_value:
        efficiency = 100.0
    else:
        efficiency = 0.0

    # Get favorite ship
    favorite_ship = None
    if ship_counts:
        favorite_ship = max(ship_counts.items(), key=lambda x: x[1])[0]

    # Calculate rank (compare kill value to all users)
    rank = None
    if kills > 0:
        # Get all users' kill values for the month
        all_participations = KillmailParticipant.objects.filter(
            killmail__killmail_time__gte=month_start,
            killmail__killmail_time__lte=month_end,
            is_victim=False,
            user__isnull=False,
        ).select_related('killmail')

        user_values = {}
        for p in all_participations:
            uid = p.user_id
            if uid not in user_values:
                user_values[uid] = {'kms': set(), 'value': Decimal('0')}
            if p.killmail_id not in user_values[uid]['kms']:
                user_values[uid]['kms'].add(p.killmail_id)
                user_values[uid]['value'] += p.killmail.total_value

        # Sort by value descending
        sorted_users = sorted(user_values.items(), key=lambda x: x[1]['value'], reverse=True)
        for i, (uid, data) in enumerate(sorted_users, 1):
            if uid == request.user.id:
                rank = i
                break

    return JsonResponse({
        'kills': kills,
        'losses': losses,
        'kill_value': float(kill_value),
        'loss_value': float(loss_value),
        'kill_value_formatted': format_isk(kill_value),
        'loss_value_formatted': format_isk(loss_value),
        'final_blows': final_blows,
        'efficiency': round(efficiency, 1),
        'rank': rank,
        'favorite_ship': favorite_ship,
    })


@login_required
@permission_required("aatps.basic_access")
def recent_kills_api(request: WSGIRequest) -> JsonResponse:
    """Returns recent killmails for the month."""
    month_start, month_end, year, month, is_current = get_month_params_from_request(request)
    limit = int(request.GET.get('limit', 50))
    user_only = request.GET.get('user_only', 'false').lower() == 'true'

    # Base query for killmails with participants
    participants_qs = KillmailParticipant.objects.filter(
        killmail__killmail_time__gte=month_start,
        killmail__killmail_time__lte=month_end,
    )

    if user_only:
        # Get user's character IDs
        user_char_ids = list(
            EveCharacter.objects.filter(
                character_ownership__user=request.user
            ).values_list('character_id', flat=True)
        )
        participants_qs = participants_qs.filter(
            character__character_id__in=user_char_ids
        )

    # Get killmail IDs and whether they are kills or losses for this user/group
    km_data = {}
    for p in participants_qs.select_related('killmail'):
        km_id = p.killmail_id
        if km_id not in km_data:
            km_data[km_id] = {
                'killmail': p.killmail,
                'is_loss': p.is_victim,
            }
        # If any participant is a victim, it's a loss
        if p.is_victim:
            km_data[km_id]['is_loss'] = True

    # Sort by time descending and limit
    sorted_kms = sorted(
        km_data.values(),
        key=lambda x: x['killmail'].killmail_time,
        reverse=True
    )[:limit]

    data = []
    for item in sorted_kms:
        km = item['killmail']
        data.append({
            'killmail_id': km.killmail_id,
            'killmail_time': km.killmail_time.isoformat(),
            'ship_type_id': km.ship_type_id,
            'ship_type_name': km.ship_type_name,
            'victim_name': km.victim_name,
            'victim_corp_name': km.victim_corp_name,
            'total_value': float(km.total_value),
            'total_value_formatted': format_isk(km.total_value),
            'solar_system_name': km.solar_system_name,
            'is_loss': item['is_loss'],
            'final_blow_char_name': km.final_blow_char_name,
        })

    return JsonResponse({'data': data})
