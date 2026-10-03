from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CNCMachine,
    FailureCategory,
    FailureSubCategory,
    SparePart,
    BreakdownTicket,
    TicketSpareUsage,
    MachineStateLog
)


@admin.register(CNCMachine)
class CNCMachineAdmin(admin.ModelAdmin):
    fields = ('line_name', 'service_frequency', 'last_service_date', 'machine_code', 'name', 'model_number', 'controller_type', 'ip_address', 'port', 'timeout', 'location', 'current_status', 'qr_code_image', 'is_active')
    list_display = ('line_name', 'service_frequency', 'last_service_date', 'machine_code', 'name', 'model_number', 'ip_address', 'port', 'status_badge', 'qr_preview', 'is_active', 'last_polled_at')
    list_filter = ('line_name', 'service_frequency', 'current_status', 'is_active', 'controller_type')
    search_fields = ('line_name', 'machine_code', 'name', 'ip_address', 'location')
    readonly_fields = ('current_status', 'last_status_change', 'last_polled_at', 'qr_preview_large', 'created_at', 'updated_at')
    actions = ['sync_focas_status']

    @admin.action(description="⚡ Poll Live Status from CNC via FOCAS")
    def sync_focas_status(self, request, queryset):
        from .focas.collector import TelemetryCollector
        success_count = 0
        fail_count = 0
        for m in queryset:
            ok, res = TelemetryCollector.poll_focas_machine(m)
            if ok:
                success_count += 1
            else:
                fail_count += 1
        self.message_user(request, f"FOCAS Polling Finished: {success_count} machine(s) online & updated, {fail_count} offline/unreachable.")

    def status_badge(self, obj):
        colors = {
            'RUNNING': '#10b981',      # Emerald green
            'IDLE': '#f59e0b',         # Amber
            'ALARM': '#ef4444',        # Red
            'EMERGENCY_STOP': '#b91c1c', # Dark red
            'UNDER_MAINTENANCE': '#3b82f6', # Blue
            'OFFLINE': '#6b7280',      # Gray
        }
        color = colors.get(obj.current_status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_current_status_display()
        )
    status_badge.short_description = 'Status'

    def qr_preview(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="40" height="40" style="border: 1px solid #ccc; border-radius: 3px;" />', obj.qr_code_image.url)
        return "-"
    qr_preview.short_description = 'QR'

    def qr_preview_large(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="200" height="200" style="border: 1px solid #ccc; border-radius: 6px;" />', obj.qr_code_image.url)
        return "No QR generated yet"
    qr_preview_large.short_description = 'Machine QR Code'


class FailureSubCategoryInline(admin.TabularInline):
    model = FailureSubCategory
    extra = 1


@admin.register(FailureCategory)
class FailureCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'sub_category_count', 'is_active')
    inlines = [FailureSubCategoryInline]

    def sub_category_count(self, obj):
        return obj.sub_categories.count()
    sub_category_count.short_description = 'Sub-Categories'


@admin.register(FailureSubCategory)
class FailureSubCategoryAdmin(admin.ModelAdmin):
    list_display = ('sub_category_code', 'name', 'category', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('sub_category_code', 'name', 'description')


@admin.register(SparePart)
class SparePartAdmin(admin.ModelAdmin):
    list_display = ('part_code', 'part_name', 'category', 'unit_price', 'stock_quantity', 'unit_of_measure', 'is_active')
    list_filter = ('category', 'unit_of_measure', 'is_active')
    search_fields = ('part_code', 'part_name', 'specification')


class TicketSpareUsageInline(admin.TabularInline):
    model = TicketSpareUsage
    extra = 1
    fields = ('spare_part', 'quantity', 'unit_price_at_use', 'line_total', 'notes')
    readonly_fields = ('line_total',)


@admin.register(BreakdownTicket)
class BreakdownTicketAdmin(admin.ModelAdmin):
    list_display = (
        'ticket_number', 'machine', 'status_badge', 'trigger_source',
        'alarm_time', 'scan_time', 'resolve_time',
        'response_time_min', 'repair_time_min', 'total_spares_cost'
    )
    list_filter = ('status', 'trigger_source', 'shift', 'machine', 'failure_sub_category__category')
    search_fields = ('ticket_number', 'machine__machine_code', 'technician__username', 'focas_alarm_code', 'symptom_notes')
    inlines = [TicketSpareUsageInline]
    readonly_fields = (
        'ticket_number', 'response_time_seconds', 'repair_time_seconds',
        'total_downtime_seconds', 'ramp_up_delay_seconds', 'total_spares_cost',
        'created_at', 'updated_at'
    )

    def status_badge(self, obj):
        colors = {
            'OPEN_ALARM': '#ef4444',
            'ACKNOWLEDGED': '#f59e0b',
            'UNDER_REPAIR': '#3b82f6',
            'RESOLVED': '#10b981',
            'CLOSED_RUNNING': '#059669',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def response_time_min(self, obj):
        if obj.response_time_seconds is not None:
            return f"{obj.response_time_seconds // 60}m {obj.response_time_seconds % 60}s"
        return "-"
    response_time_min.short_description = 'Response (MTTA)'

    def repair_time_min(self, obj):
        if obj.repair_time_seconds is not None:
            return f"{obj.repair_time_seconds // 60}m {obj.repair_time_seconds % 60}s"
        return "-"
    repair_time_min.short_description = 'Repair Time'


@admin.register(MachineStateLog)
class MachineStateLogAdmin(admin.ModelAdmin):
    list_display = ('machine', 'state', 'start_time', 'end_time', 'duration_seconds', 'run', 'alarm', 'emergency')
    list_filter = ('state', 'machine')
    search_fields = ('machine__machine_code',)

