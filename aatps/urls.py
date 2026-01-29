"""App URLs"""

# Django
from django.urls import path

# AA Campaign
# AA TPS
from aatps import views

app_name: str = "aatps"

urlpatterns = [
    # Main dashboard (current month)
    path("", views.dashboard, name="dashboard"),
    # API endpoints for dynamic data loading
    path("api/leaderboard/", views.leaderboard_api, name="leaderboard_api"),
    path("api/activity/", views.activity_api, name="activity_api"),
    path("api/stats/", views.stats_api, name="stats_api"),
    path("api/top-kills/", views.top_kills_api, name="top_kills_api"),
    path("api/ship-stats/", views.ship_stats_api, name="ship_stats_api"),
    path("api/my-stats/", views.my_stats_api, name="my_stats_api"),
    path("api/recent-kills/", views.recent_kills_api, name="recent_kills_api"),
    # Historical view for past months
    path("history/<int:year>/<int:month>/", views.historical_view, name="historical"),
]
