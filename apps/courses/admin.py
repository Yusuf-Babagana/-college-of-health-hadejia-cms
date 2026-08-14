from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import Course, CourseOffering, CourseRegistration


@admin.register(Course)
class CourseAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """Fieldsets exist purely to explain how Programme, Eligible
    Programmes, and General Studies interact - this business rule has
    tripped up real data entry before (a course invisible on every
    Master Broadsheet because none of the three was set). No fields are
    added or removed versus the previous flat layout, just grouped and
    annotated.
    """
    list_display = (
        'code', 'title', 'credit_units', 'level', 'semester_name', 'department', 'programme', 'is_deleted',
    )
    list_filter = SoftDeleteAdminMixin.list_filter + ('level', 'semester_name', 'department')
    search_fields = ('code', 'title')
    autocomplete_fields = ('department', 'programme')
    filter_horizontal = ('eligible_departments', 'eligible_programmes')
    ordering = ('code',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('code', 'title', 'credit_units', 'level', 'semester_name', 'department'),
        }),
        ('Programme', {
            'fields': ('programme', 'eligible_departments', 'eligible_programmes'),
            'description': (
                '<strong>Programme</strong> is this course’s owning/default programme - leave it blank '
                'for a course that isn’t tied to one specific programme.<br>'
                '<strong>Eligible Departments/Programmes</strong> are EXTRA departments/programmes '
                '(besides the course’s own Department/Programme above) that may also take it - use this '
                'to cross-list a course shared by a couple of programmes, e.g. one taken by both a Diploma '
                'and a Certificate track.<br>'
                '<strong>General Studies</strong>: for a truly college-wide course (e.g. Use of English), '
                'leave Programme blank AND Eligible Programmes empty - as long as this course’s '
                'Department has “General Studies” checked, it becomes automatically available to '
                'every programme without needing to be listed here. Setting an explicit Programme or '
                'Eligible Programmes on a General Studies course narrows it to just those, overriding the '
                'automatic “everyone” behavior.'
            ),
        }),
        ('Bookkeeping', {
            'fields': ('id', 'created_at', 'updated_at', 'is_deleted', 'deleted_at'),
            'classes': ('collapse',),
        }),
    )


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
