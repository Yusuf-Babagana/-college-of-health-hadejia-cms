from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import Department


@admin.register(Department)
class DepartmentAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'code', 'hod', 'is_deleted')
    search_fields = ('name', 'code')
    ordering = ('name',)
    autocomplete_fields = ('hod',)
    readonly_fields = ('id', 'created_at', 'updated_at')
