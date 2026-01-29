"""App Configuration"""

# Django
from django.apps import AppConfig

# AA TPS
from aatps import __version__


class AaTpsConfig(AppConfig):
    """App Config"""

    name = "aatps"
    label = "aatps"
    verbose_name = f"AA TPS v{__version__}"
