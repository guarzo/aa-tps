"""App Views"""

# Django
from django.contrib.auth.decorators import login_required, permission_required
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from .models import Campaign, CampaignKillmail

@login_required
@permission_required("aacampaign.basic_access")
def index(request: WSGIRequest) -> HttpResponse:
    """List of active campaigns"""
    campaigns = Campaign.objects.filter(is_active=True).order_by('-start_date')
    context = {"campaigns": campaigns}
    return render(request, "aacampaign/index.html", context)

@login_required
@permission_required("aacampaign.basic_access")
def campaign_details(request: WSGIRequest, campaign_id: int) -> HttpResponse:
    """Leaderboard and stats for a campaign"""
    campaign = get_object_or_404(Campaign, id=campaign_id)

    # Overall stats
    stats = campaign.killmails.aggregate(
        total_kills=Count('id', filter=Q(is_loss=False)),
        total_kill_value=Sum('total_value', filter=Q(is_loss=False)),
        total_losses=Count('id', filter=Q(is_loss=True)),
        total_loss_value=Sum('total_value', filter=Q(is_loss=True))
    )

    # Calculate efficiency
    if stats['total_kill_value'] and stats['total_loss_value']:
        efficiency = (stats['total_kill_value'] / (stats['total_kill_value'] + stats['total_loss_value'])) * 100
    elif stats['total_kill_value']:
        efficiency = 100
    else:
        efficiency = 0

    # Top kills for the bar
    top_kills = campaign.killmails.filter(
        is_loss=False
    ).order_by('-total_value')[:10]

    # Ship Class stats
    ship_stats_raw = campaign.killmails.values('ship_group_name', 'is_loss').annotate(count=Count('id'))
    ship_stats = {}
    for entry in ship_stats_raw:
        group = entry['ship_group_name'] or "Unknown"
        if group not in ship_stats:
            ship_stats[group] = {'killed': 0, 'lost': 0}
        if entry['is_loss']:
            ship_stats[group]['lost'] += entry['count']
        else:
            ship_stats[group]['killed'] += entry['count']

    # Sort ship stats by group name
    ship_stats = dict(sorted(ship_stats.items()))

    # Recent killmails for the new tab
    recent_killmails = campaign.killmails.select_related(
        'solar_system', 'solar_system__eve_constellation__eve_region'
    ).prefetch_related('attackers').order_by('-killmail_time')[:1000]

    context = {
        "campaign": campaign,
        "stats": stats,
        "efficiency": efficiency,
        "top_kills": top_kills,
        "ship_stats": ship_stats,
        "recent_killmails": recent_killmails,
    }
    return render(request, "aacampaign/campaign_details.html", context)

@login_required
@permission_required("aacampaign.basic_access")
def leaderboard_data(request: WSGIRequest, campaign_id: int) -> JsonResponse:
    """JSON data for the leaderboard DataTable"""
    campaign = get_object_or_404(Campaign, id=campaign_id)

    # DataTables parameters
    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 10))
    search_value = request.GET.get('search[value]', '')

    # Queryset
    queryset = campaign.killmails.filter(
        is_loss=False,
        attackers__isnull=False
    ).values(
        'attackers__id',
        'attackers__character_name'
    ).annotate(
        kills=Count('id'),
        kill_value=Sum('total_value')
    )

    records_total = queryset.count()

    if search_value:
        queryset = queryset.filter(attackers__character_name__icontains(search_value))

    records_filtered = queryset.count()

    # Top 5 by value for badges (absolute rank)
    top_5_ids = list(campaign.killmails.filter(
        is_loss=False,
        attackers__isnull=False
    ).values(
        'attackers__id'
    ).annotate(
        total_val=Sum('total_value')
    ).order_by('-total_val')[:5].values_list('attackers__id', flat=True))

    # Ordering
    order_column_index = request.GET.get('order[0][column]')
    order_dir = request.GET.get('order[0][dir]', 'desc')

    columns = {
        '0': 'attackers__character_name',
        '1': 'kills',
        '2': 'kill_value',
    }

    sort_column = columns.get(order_column_index, 'kill_value')
    if order_dir == 'desc':
        sort_column = f"-{sort_column}"

    queryset = queryset.order_by(sort_column)

    # Paging
    queryset = queryset[start:start + length]

    data = []
    for entry in queryset:
        char_id = entry['attackers__id']
        abs_rank = None
        if char_id in top_5_ids:
            abs_rank = top_5_ids.index(char_id) + 1

        data.append({
            'rank': abs_rank,
            'character_name': entry['attackers__character_name'],
            'kills': entry['kills'],
            'kill_value': float(entry['kill_value']) if entry['kill_value'] else 0.0,
        })

    return JsonResponse({
        'draw': draw,
        'recordsTotal': records_total,
        'recordsFiltered': records_filtered,
        'data': data,
    })
