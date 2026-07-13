from django.contrib import admin
from django.contrib.admin.apps import AdminConfig
from django.db.models import Count


class CollegeAdminSite(admin.AdminSite):
    """Custom admin site so the index view can carry real statistics.

    Wired in via CollegeAdminConfig.default_site below, rather than by
    reassigning django.contrib.admin.site directly - this is the officially
    documented way to swap the admin site without touching any Django core
    files, and it survives Django upgrades.
    """

    site_header = 'College of Health Sciences and Technology, Hadejia'
    site_title = 'COHST Admin'
    index_title = 'Administration Dashboard'

    def index(self, request, extra_context=None):
        from django.contrib.auth.models import Group

        from apps.accounts.models import User

        extra_context = extra_context or {}
        extra_context['dashboard_stats'] = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'total_groups': Group.objects.count(),
            'role_breakdown': User.objects.values('role')
            .annotate(count=Count('id'))
            .order_by('role'),
        }
        return super().index(request, extra_context=extra_context)


class CollegeAdminConfig(AdminConfig):
    """Replaces 'django.contrib.admin' in INSTALLED_APPS so the project
    uses CollegeAdminSite above. This is Django's own documented mechanism
    for overriding the default admin site (AdminConfig.default_site).
    """

    default_site = 'apps.core.admin_site.CollegeAdminSite'
