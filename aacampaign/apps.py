"""App Configuration"""

# Django
from django.apps import AppConfig

# AA Campaign
from aacampaign import __version__


class AaCampaignConfig(AppConfig):
    """App Config"""

    name = "aacampaign"
    label = "aacampaign"
    verbose_name = f"AA Campaign v{__version__}"
