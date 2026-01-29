"""
Database models for AA TPS (Total Participation Statistics).

This module defines the data models for tracking EVE Online killmail
participation for Alliance Auth users.
"""

# Django
from django.db import models


class MonthlyKillmail(models.Model):
    """
    Stores killmail data fetched from zKillboard.

    This model represents a single killmail from EVE Online, containing
    information about the victim, the ship destroyed, location, and value.
    Killmails are linked to authenticated users through KillmailParticipant.

    Attributes:
        killmail_id: Unique identifier from EVE Online/zKillboard
        killmail_time: When the kill occurred (UTC)
        solar_system_id: EVE solar system ID where the kill happened
        solar_system_name: Name of the solar system
        region_id: EVE region ID
        region_name: Name of the region
        ship_type_id: EVE type ID of the destroyed ship
        ship_type_name: Name of the destroyed ship
        ship_group_name: Ship class/group (e.g., "Frigate", "Battleship")
        victim_id: Character ID of the victim (0 if NPC)
        victim_name: Name of the victim
        victim_corp_id: Corporation ID of the victim
        victim_corp_name: Corporation name of the victim
        victim_alliance_id: Alliance ID of the victim (nullable)
        victim_alliance_name: Alliance name of the victim (nullable)
        final_blow_char_id: Character ID who dealt the final blow
        final_blow_char_name: Name of the character who dealt final blow
        final_blow_corp_id: Corporation ID of final blow dealer
        final_blow_corp_name: Corporation name of final blow dealer
        final_blow_alliance_id: Alliance ID of final blow dealer (nullable)
        final_blow_alliance_name: Alliance name of final blow dealer (nullable)
        total_value: ISK value of the killmail from zKillboard
        zkill_hash: Hash for ESI killmail lookups
    """
    killmail_id = models.PositiveBigIntegerField(unique=True, primary_key=True)
    killmail_time = models.DateTimeField(db_index=True)
    solar_system_id = models.PositiveIntegerField()
    solar_system_name = models.CharField(max_length=255, default="Unknown")
    region_id = models.PositiveIntegerField(null=True)
    region_name = models.CharField(max_length=255, default="Unknown")

    # Ship info
    ship_type_id = models.PositiveIntegerField(default=0)
    ship_type_name = models.CharField(max_length=255, default="Unknown")
    ship_group_name = models.CharField(max_length=255, default="Unknown")

    # Victim info
    victim_id = models.PositiveIntegerField(default=0)
    victim_name = models.CharField(max_length=255, default="Unknown")
    victim_corp_id = models.PositiveIntegerField(default=0)
    victim_corp_name = models.CharField(max_length=255, default="Unknown")
    victim_alliance_id = models.PositiveIntegerField(null=True, blank=True)
    victim_alliance_name = models.CharField(max_length=255, null=True, blank=True)

    # Final blow info
    final_blow_char_id = models.PositiveIntegerField(default=0)
    final_blow_char_name = models.CharField(max_length=255, default="Unknown")
    final_blow_corp_id = models.PositiveIntegerField(default=0)
    final_blow_corp_name = models.CharField(max_length=255, default="Unknown")
    final_blow_alliance_id = models.PositiveIntegerField(null=True, blank=True)
    final_blow_alliance_name = models.CharField(max_length=255, null=True, blank=True)

    # Value
    total_value = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    # Hash for ESI lookups
    zkill_hash = models.CharField(max_length=64, default="")

    class Meta:
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access this app"),
        )
        indexes = [
            models.Index(fields=['killmail_time', 'total_value'], name='aatps_km_time_value_idx'),
        ]

    def __str__(self):
        return f"Killmail {self.killmail_id} - {self.victim_name}"


class KillmailParticipant(models.Model):
    """
    Links authenticated Alliance Auth users to killmails they participated in.

    This model creates a many-to-many relationship between killmails and
    characters, tracking whether each character was a victim or attacker,
    and additional participation details.

    Attributes:
        killmail: The killmail this participation is for
        character: The EVE character who participated
        user: The Alliance Auth user (if character is authenticated)
        is_victim: True if the character was the victim
        is_final_blow: True if the character dealt the final blow
        damage_done: Amount of damage dealt (0 for victims)
        ship_type_id: EVE type ID of the ship used
        ship_type_name: Name of the ship used
    """
    killmail = models.ForeignKey(
        MonthlyKillmail,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    character = models.ForeignKey(
        'eveonline.EveCharacter',
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        'authentication.User',
        on_delete=models.CASCADE,
        null=True
    )
    is_victim = models.BooleanField(default=False)
    is_final_blow = models.BooleanField(default=False)
    damage_done = models.PositiveIntegerField(default=0)
    ship_type_id = models.PositiveIntegerField(default=0)
    ship_type_name = models.CharField(max_length=255, default="Unknown")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['killmail', 'character'],
                name='unique_killmail_participant'
            )
        ]
        indexes = [
            models.Index(fields=['is_victim'], name='aatps_parti_is_vict_idx'),
            models.Index(fields=['is_final_blow'], name='aatps_parti_final_blow_idx'),
            models.Index(fields=['user', 'is_victim'], name='aatps_parti_user_victim_idx'),
        ]

    def __str__(self):
        role = "victim" if self.is_victim else "attacker"
        return f"{self.character} ({role}) on {self.killmail.killmail_id}"
