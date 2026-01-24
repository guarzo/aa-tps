"""App URLs"""

# Django
from django.urls import path

# AA Campaign
from aacampaign import views

app_name: str = "aacampaign"  # pylint: disable=invalid-name

urlpatterns = [
    path("", views.index, name="index"),
    path("campaign/<int:campaign_id>/", views.campaign_details, name="campaign_details"),
    path("campaign/<int:campaign_id>/leaderboard-data/", views.leaderboard_data, name="leaderboard_data"),
]
