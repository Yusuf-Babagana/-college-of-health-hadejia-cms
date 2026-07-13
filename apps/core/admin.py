from django.contrib import admin


class SoftDeleteAdminMixin:
    """Mix into a ModelAdmin for any model based on SoftDeleteModel/BaseModel
    to get an is_deleted filter plus bulk archive/restore actions, and to
    make sure archived rows are visible in the admin (which otherwise only
    ever sees the default, non-deleted manager).
    """

    list_filter = ('is_deleted',)
    actions = ('archive_selected', 'restore_selected')

    def get_queryset(self, request):
        qs = self.model.all_objects.all()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    @admin.action(description='Archive selected (soft delete)')
    def archive_selected(self, request, queryset):
        for obj in queryset:
            obj.delete()

    @admin.action(description='Restore selected')
    def restore_selected(self, request, queryset):
        for obj in queryset:
            obj.restore()
