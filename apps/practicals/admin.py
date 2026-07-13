from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import PracticalPlacement


@admin.register(PracticalPlacement)
class PracticalPlacementAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('student', 'cadre', 'state_of_practical', 'lga_of_practical', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + (
        'invoice__fee_structure__fee_type', 'invoice__fee_structure__session',
    )
    search_fields = ('student__matric_number', 'student__user__first_name', 'student__user__last_name')
    autocomplete_fields = ('student', 'invoice')
    readonly_fields = ('id', 'created_at', 'updated_at')
