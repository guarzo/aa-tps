# Django
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add performance indexes for frequently filtered fields.

    This migration adds indexes to improve query performance on:
    - KillmailParticipant.is_victim: Frequently used to filter kills vs losses
    - KillmailParticipant.is_final_blow: Used for final blow statistics
    - KillmailParticipant (user, is_victim): Composite index for user-specific queries
    - MonthlyKillmail (killmail_time, total_value): For time-range value queries
    """

    dependencies = [
        ("aatps", "0008_remove_legacy_models"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="killmailparticipant",
            index=models.Index(fields=["is_victim"], name="aatps_parti_is_vict_idx"),
        ),
        migrations.AddIndex(
            model_name="killmailparticipant",
            index=models.Index(fields=["is_final_blow"], name="aatps_parti_final_blow_idx"),
        ),
        migrations.AddIndex(
            model_name="killmailparticipant",
            index=models.Index(fields=["user", "is_victim"], name="aatps_parti_user_victim_idx"),
        ),
        migrations.AddIndex(
            model_name="monthlykillmail",
            index=models.Index(fields=["killmail_time", "total_value"], name="aatps_km_time_value_idx"),
        ),
    ]
