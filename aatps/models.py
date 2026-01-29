"""
App Models
Create your models in here
"""

# Django
from django.db import models


class MonthlyKillmail(models.Model):
    """Killmail data not tied to a specific campaign."""
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

    def __str__(self):
        return f"Killmail {self.killmail_id} - {self.victim_name}"


class KillmailParticipant(models.Model):
    """Links auth users to killmails they participated in."""
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
        unique_together = ('killmail', 'character')

    def __str__(self):
        role = "victim" if self.is_victim else "attacker"
        return f"{self.character} ({role}) on {self.killmail.killmail_id}"
