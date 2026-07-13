from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'role', 'is_active_account', 'is_active', 'is_staff',
    )
    list_display_links = ('username',)
    list_filter = ('role', 'is_active_account', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    date_hierarchy = 'date_joined'
    list_per_page = 25
    readonly_fields = ('id', 'date_joined', 'last_login', 'created_at', 'updated_at')

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role & Contact', {
            'fields': ('role', 'phone_number', 'avatar', 'must_change_password', 'is_active_account'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Role & Contact', {
            'fields': ('role', 'email', 'phone_number'),
        }),
    )


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):
    """Groups double as this project's RBAC roles, so they're worth their
    own polished admin rather than the bare default registration.
    """
    list_display = ('name', 'permission_count')
    search_fields = ('name',)
    ordering = ('name',)

    @admin.display(description='Permissions')
    def permission_count(self, obj):
        return obj.permissions.count()
