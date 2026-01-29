"""
Admin models for AA TPS.

This module provides read-only admin interfaces for inspecting killmail data.
The admin is intentionally read-only to prevent accidental data corruption -
all data is pulled automatically from zKillboard.
"""

from django.contrib import admin
from .models import (
    MonthlyKillmail,
    KillmailParticipant,
)
from .utils import format_isk


class ReadOnlyAdminMixin:
    """
    Mixin that makes an admin interface read-only.

    Use this for models where data is automatically collected and
    should not be manually modified.
    """

    def has_add_permission(self, request):
        """Disable adding records manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing records."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting records."""
        return False


@admin.register(MonthlyKillmail)
class MonthlyKillmailAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only admin interface for viewing killmail data."""

    list_display = (
        'killmail_id',
        'killmail_time',
        'ship_type_name',
        'victim_name',
        'victim_corp_name',
        'solar_system_name',
        'formatted_value',
    )
    list_filter = (
        'killmail_time',
        'ship_group_name',
        'region_name',
    )
    search_fields = (
        'killmail_id',
        'victim_name',
        'victim_corp_name',
        'victim_alliance_name',
        'ship_type_name',
        'solar_system_name',
        'final_blow_char_name',
    )
    date_hierarchy = 'killmail_time'
    ordering = ('-killmail_time',)

    @admin.display(description='Value (ISK)')
    def formatted_value(self, obj):
        """Format the total value with ISK suffix."""
        return format_isk(obj.total_value)


@admin.register(KillmailParticipant)
class KillmailParticipantAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only admin interface for viewing killmail participants."""

    list_display = (
        'killmail',
        'character',
        'user',
        'is_victim',
        'is_final_blow',
        'damage_done',
        'ship_type_name',
    )
    list_filter = (
        'is_victim',
        'is_final_blow',
        'killmail__killmail_time',
    )
    search_fields = (
        'character__character_name',
        'user__username',
        'ship_type_name',
        'killmail__killmail_id',
    )
    raw_id_fields = ('killmail', 'character', 'user')
    ordering = ('-killmail__killmail_time',)
