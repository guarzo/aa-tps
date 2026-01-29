"""App Settings"""

# Django
from django.conf import settings

# =============================================================================
# Data Retention Settings
# =============================================================================

# How many months of killmail data to retain (default: 12 months)
# Older data will be automatically cleaned up by the cleanup_old_killmails task
AA_TPS_RETENTION_MONTHS = getattr(settings, "AA_TPS_RETENTION_MONTHS", 12)

# =============================================================================
# Data Pull Settings
# =============================================================================

# How often to pull data (in seconds, for pastSeconds API) - default 1 hour
AA_TPS_PULL_INTERVAL = getattr(settings, "AA_TPS_PULL_INTERVAL", 3600)

# =============================================================================
# Feature Flags
# =============================================================================

# Enable/disable personal stats feature on the dashboard
AA_TPS_SHOW_PERSONAL_STATS = getattr(settings, "AA_TPS_SHOW_PERSONAL_STATS", True)
