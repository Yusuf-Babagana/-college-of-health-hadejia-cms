from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import Student


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
