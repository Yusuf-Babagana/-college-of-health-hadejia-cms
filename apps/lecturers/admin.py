from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import Lecturer


@admin.register(Lecturer)
class LecturerAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'department', 'qualification', 'appointment_date', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + ('department',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'qualification')
    autocomplete_fields = ('user', 'department')
    ordering = ('user__first_name', 'user__last_name')
    readonly_fields = ('id', 'created_at', 'updated_at')
