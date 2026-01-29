"""Test factories for AA TPS models."""

# Standard Library
from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal

# Django
from django.contrib.auth import get_user_model

# Alliance Auth
from allianceauth.eveonline.models import EveCharacter

# AA Campaign
from aatps.models import KillmailParticipant, MonthlyKillmail

User = get_user_model()


class MonthlyKillmailFactory:
    """Factory for creating MonthlyKillmail test instances."""

    _counter = 0

    @classmethod
    def create(
        cls,
        killmail_id: int = None,
        killmail_time: datetime = None,
        solar_system_id: int = 30000142,
        solar_system_name: str = "Jita",
        region_id: int = 10000002,
        region_name: str = "The Forge",
        ship_type_id: int = 587,
        ship_type_name: str = "Rifter",
        ship_group_name: str = "Frigate",
        victim_id: int = 123456789,
        victim_name: str = "Test Victim",
        victim_corp_id: int = 98000001,
        victim_corp_name: str = "Test Corp",
        victim_alliance_id: int = None,
        victim_alliance_name: str = None,
        total_value: Decimal = Decimal("1000000.00"),
        **kwargs,
    ) -> MonthlyKillmail:
        """Create a MonthlyKillmail instance."""
        cls._counter += 1

        if killmail_id is None:
            killmail_id = 100000 + cls._counter

        if killmail_time is None:
            killmail_time = datetime.now(dt_timezone.utc)

        return MonthlyKillmail.objects.create(
            killmail_id=killmail_id,
            killmail_time=killmail_time,
            solar_system_id=solar_system_id,
            solar_system_name=solar_system_name,
            region_id=region_id,
            region_name=region_name,
            ship_type_id=ship_type_id,
            ship_type_name=ship_type_name,
            ship_group_name=ship_group_name,
            victim_id=victim_id,
            victim_name=victim_name,
            victim_corp_id=victim_corp_id,
            victim_corp_name=victim_corp_name,
            victim_alliance_id=victim_alliance_id,
            victim_alliance_name=victim_alliance_name,
            total_value=total_value,
            **kwargs,
        )

    @classmethod
    def reset_counter(cls):
        """Reset the counter (useful between test runs)."""
        cls._counter = 0


class KillmailParticipantFactory:
    """Factory for creating KillmailParticipant test instances."""

    @classmethod
    def create(
        cls,
        killmail: MonthlyKillmail,
        character: EveCharacter,
        user: User = None,
        is_victim: bool = False,
        is_final_blow: bool = False,
        damage_done: int = 1000,
        ship_type_id: int = 587,
        ship_type_name: str = "Rifter",
    ) -> KillmailParticipant:
        """Create a KillmailParticipant instance."""
        return KillmailParticipant.objects.create(
            killmail=killmail,
            character=character,
            user=user,
            is_victim=is_victim,
            is_final_blow=is_final_blow,
            damage_done=damage_done,
            ship_type_id=ship_type_id,
            ship_type_name=ship_type_name,
        )
