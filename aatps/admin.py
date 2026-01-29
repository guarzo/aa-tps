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


@admin.register(MonthlyKillmail)
class MonthlyKillmailAdmin(admin.ModelAdmin):
    """
    Read-only admin interface for viewing killmail data.

    This admin allows inspection of killmail data pulled from zKillboard.
    All fields are read-only to prevent accidental modification of
    automatically collected data.
    """

    # Display configuration
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

    # Read-only configuration - prevent accidental edits
    def has_add_permission(self, request):
        """Disable adding killmails manually - data comes from zKillboard."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing killmails - data integrity from zKillboard."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting individual killmails - use cleanup task instead."""
        return False

    @admin.display(description='Value (ISK)')
    def formatted_value(self, obj):
        """Format the total value with ISK suffix."""
        if obj.total_value >= 1_000_000_000:
            return f"{obj.total_value / 1_000_000_000:.2f}B"
        elif obj.total_value >= 1_000_000:
            return f"{obj.total_value / 1_000_000:.2f}M"
        elif obj.total_value >= 1_000:
            return f"{obj.total_value / 1_000:.2f}K"
        return f"{obj.total_value:.0f}"


@admin.register(KillmailParticipant)
class KillmailParticipantAdmin(admin.ModelAdmin):
    """
    Read-only admin interface for viewing killmail participants.

    This admin allows inspection of which authenticated users participated
    in each killmail. All fields are read-only.
    """

    # Display configuration
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

    # Read-only configuration
    def has_add_permission(self, request):
        """Disable adding participants manually - data comes from zKillboard."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing participants - data integrity from zKillboard."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting participants - use cleanup task instead."""
        return False
