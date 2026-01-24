"""App Settings"""

# Django
from django.conf import settings

# AA Campaign settings
AA_CAMPAIGN_SETTING_ONE = getattr(settings, "AA_CAMPAIGN_SETTING_ONE", None)
