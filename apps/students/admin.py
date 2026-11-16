from django.contrib import admin, messages
from django.template.response import TemplateResponse

from apps.core.admin import SoftDeleteAdminMixin

from . import services
from .models import Guardian, Student


class GuardianInline(admin.StackedInline):
    model = Guardian
    extra = 0
    max_num = 1
    can_delete = False


@admin.register(Student)
class StudentAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """Registrar-facing student records are created by the (separate)
    Admission portal; this admin registration is the fallback way to get
    Student rows into the system until that integration exists.
    """
    list_display = (
        'matric_number', 'user', 'department', 'programme', 'level', 'status', 'admission_session', 'is_deleted',
    )
    list_filter = SoftDeleteAdminMixin.list_filter + ('department', 'level', 'status', 'admission_session')
    search_fields = ('matric_number', 'user__username', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('user', 'department', 'programme', 'admission_session')
    ordering = ('matric_number',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    actions = SoftDeleteAdminMixin.actions + ('promote_selected',)
    inlines = (GuardianInline,)

    @admin.action(description='Promote selected students to the next level', permissions=('change',))
    def promote_selected(self, request, queryset):
        """Tick students, choose this action, review the counts, confirm.
        Only active students move; those at their programme's final level
        are left alone (mark them Graduated)."""
        students = list(queryset.select_related('programme', 'user'))
        if request.POST.get('confirm') == '1':
            promoted, at_final, not_active = services.promote_many(students)
            self.message_user(
                request,
                f'Promoted {promoted} student(s) to the next level.'
                + (f' {at_final} at their final level and {not_active} inactive/archived were left unchanged.'
                   if at_final or not_active else ''),
                messages.SUCCESS if promoted else messages.WARNING,
            )
            return None
        movable, at_final, not_active = services.classify_for_promotion(students)
        context = {
            **self.admin_site.each_context(request),
            'title': 'Promote students',
            'opts': self.model._meta,
            'queryset': students,
            'movable': movable,
            'at_final': at_final,
            'not_active': not_active,
            'movable_rows': [(s, s.get_level_display(), dict(s._meta.get_field('level').choices)[services.next_level_for(s)]) for s in movable],
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, 'admin/students/student/promote_confirmation.html', context)
