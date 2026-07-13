from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import Grade, GradeBand


@admin.register(GradeBand)
class GradeBandAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('letter', 'min_score', 'max_score', 'grade_point', 'is_deleted')
    ordering = ('-min_score',)


@admin.register(Grade)
class GradeAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        'student', 'course_offering', 'ca_score', 'exam_score', 'total_score',
        'letter_grade', 'status', 'is_deleted',
    )
    list_filter = SoftDeleteAdminMixin.list_filter + ('status', 'course_offering__semester')
    search_fields = ('student__matric_number', 'course_offering__course__code')
    autocomplete_fields = ('student', 'course_offering', 'reviewed_by')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
