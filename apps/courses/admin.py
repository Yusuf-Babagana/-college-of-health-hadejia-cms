from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import Course, CourseOffering, CourseRegistration


@admin.register(Course)
class CourseAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        'code', 'title', 'credit_units', 'level', 'semester_name', 'department', 'programme', 'is_deleted',
    )
    list_filter = SoftDeleteAdminMixin.list_filter + ('level', 'semester_name', 'department')
    search_fields = ('code', 'title')
    autocomplete_fields = ('department', 'programme')
    filter_horizontal = ('eligible_departments', 'eligible_programmes')
    ordering = ('code',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(CourseOffering)
class CourseOfferingAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('course', 'semester', 'lecturer', 'capacity', 'registered_count', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + ('semester', 'course__department')
    search_fields = ('course__code', 'course__title')
    autocomplete_fields = ('course', 'semester', 'lecturer')
    ordering = ('-semester__session__name', 'course__code')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(CourseRegistration)
class CourseRegistrationAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('student', 'course_offering', 'status', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + ('status', 'course_offering__semester')
    search_fields = ('student__matric_number', 'course_offering__course__code')
    autocomplete_fields = ('student', 'course_offering')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
