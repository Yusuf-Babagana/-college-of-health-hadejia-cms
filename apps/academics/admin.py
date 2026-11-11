from django import forms
from django.contrib import admin

from apps.core.admin import SoftDeleteAdminMixin

from apps.core.constants import Level

from . import selectors
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


class _CascadingFilter(admin.SimpleListFilter):
    """Shared behaviour for the Programme -> Level -> Semester-Session
    filter chain: picking a value drops every dependent filter's
    selection, and a dependent filter is hidden until its parent is set.
    """
    dependents = ()
    parent_param = None

    def __init__(self, request, params, model, model_admin):
        self.request = request
        super().__init__(request, params, model, model_admin)

    def has_output(self):
        if self.parent_param and not self.request.GET.get(self.parent_param):
            return False
        return super().has_output()

    def choices(self, changelist):
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name, *self.dependents]),
            'display': 'All',
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string(
                    {self.parameter_name: lookup}, remove=list(self.dependents),
                ),
                'display': title,
            }


class ProgrammeFilter(_CascadingFilter):
    title = '1. Program'
    parameter_name = 'programme'
    dependents = ('level_sel', 'semester_sel')

    def lookups(self, request, model_admin):
        return [(p.pk, p.name) for p in selectors.get_active_programmes()]

    def queryset(self, request, queryset):
        return queryset.filter(programme_id=self.value()) if self.value() else queryset


class LevelFilter(_CascadingFilter):
    title = '2. Level'
    parameter_name = 'level_sel'
    parent_param = 'programme'
    dependents = ('semester_sel',)

    def lookups(self, request, model_admin):
        programme = selectors.get_active_programmes().filter(pk=request.GET.get('programme')).first()
        return selectors.get_levels_for_programme(programme) if programme else []

    def queryset(self, request, queryset):
        return queryset.filter(level=self.value()) if self.value() else queryset


class SemesterSessionFilter(_CascadingFilter):
    title = '3. Semester - Session'
    parameter_name = 'semester_sel'
    parent_param = 'level_sel'

    def lookups(self, request, model_admin):
        return [(s.pk, str(s)) for s in selectors.get_semesters_for_selection()]

    def queryset(self, request, queryset):
        return queryset.filter(semester_id=self.value()) if self.value() else queryset


class LevelSemesterStateAdminForm(forms.ModelForm):
    class Meta:
        model = LevelSemesterState
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        programme, level = cleaned.get('programme'), cleaned.get('level')
        if programme and level and level not in programme.levels:
            self.add_error('level', f'{programme} does not have a {dict(Level.choices)[level]}.')
        return cleaned


@admin.register(LevelSemesterState)
class LevelSemesterStateAdmin(admin.ModelAdmin):
    form = LevelSemesterStateAdminForm
    list_display = ('__str__', 'programme', 'level', 'semester')
    list_filter = (ProgrammeFilter, LevelFilter, SemesterSessionFilter)
    list_select_related = ('programme', 'semester', 'semester__session')
    autocomplete_fields = ('semester',)
    ordering = ('level', 'programme__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
