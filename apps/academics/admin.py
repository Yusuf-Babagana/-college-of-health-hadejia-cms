from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from .models import AcademicSession, LevelSemesterState, Semester


@admin.register(AcademicSession)
class AcademicSessionAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_deleted')
    search_fields = ('name',)
    ordering = ('-name',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Semester)
class SemesterAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('__str__', 'session', 'name', 'registration_start', 'registration_end', 'is_deleted')
    list_filter = SoftDeleteAdminMixin.list_filter + ('session', 'name')
    search_fields = ('session__name',)
    autocomplete_fields = ('session',)
    ordering = ('-session__name', 'name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(LevelSemesterState)
class LevelSemesterStateAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'level', 'semester')
    list_filter = ('level',)
    autocomplete_fields = ('semester',)
    ordering = ('level',)
    readonly_fields = ('id', 'created_at', 'updated_at')
