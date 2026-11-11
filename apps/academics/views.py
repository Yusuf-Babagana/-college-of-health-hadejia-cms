from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView, View

from apps.core.constants import Level, Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin

from . import selectors, services
from .forms import (
    AcademicSessionForm,
    LevelSemesterSelectionForm,
    LevelSemesterStateForm,
    RegistrationWindowForm,
    SemesterForm,
)
from .models import AcademicSession, LevelSemesterState, Semester


class AcademicManagementRoleMixin(RoleRequiredMixin):
    """FR-REG-01/02/03: session/semester management is the Registrar's
    job, not ICT Admin's - so this deliberately does NOT include
    Role.ICT_ADMIN, unlike the department/course/lecturer mixins.
    """
    allowed_roles = (Role.REGISTRAR, Role.SUPER_ADMIN)


class SessionListView(AcademicManagementRoleMixin, PaginatedListMixin, ListView):
    template_name = 'academics/session_list.html'
    context_object_name = 'sessions'

    def get_queryset(self):
        return selectors.get_session_list(
            search=self.request.GET.get('q'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class SessionCreateView(AcademicManagementRoleMixin, CreateView):
    model = AcademicSession
    form_class = AcademicSessionForm
    template_name = 'academics/session_form.html'
    success_url = reverse_lazy('academics:session_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Academic Session'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Academic session "{form.instance.name}" created.')
        return super().form_valid(form)


class SessionUpdateView(AcademicManagementRoleMixin, UpdateView):
    model = AcademicSession
    form_class = AcademicSessionForm
    template_name = 'academics/session_form.html'
    success_url = reverse_lazy('academics:session_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object.name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Academic session "{form.instance.name}" updated.')
        return super().form_valid(form)


class SessionArchiveToggleView(AcademicManagementRoleMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(AcademicSession.all_objects, pk=pk)
        if session.is_deleted:
            services.restore_session(session)
            messages.success(request, f'Session "{session.name}" restored.')
        else:
            services.archive_session(session)
            messages.success(request, f'Session "{session.name}" archived.')
        return redirect('academics:session_list')


class SemesterListView(AcademicManagementRoleMixin, PaginatedListMixin, ListView):
    template_name = 'academics/semester_list.html'
    context_object_name = 'semesters'

    def get_queryset(self):
        return selectors.get_semester_list(
            session=self.request.GET.get('session'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = selectors.get_active_sessions()
        context['current_session'] = self.request.GET.get('session', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class SemesterCreateView(AcademicManagementRoleMixin, CreateView):
    model = Semester
    form_class = SemesterForm
    template_name = 'academics/semester_form.html'
    success_url = reverse_lazy('academics:semester_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Semester'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Semester "{form.instance}" created.')
        return super().form_valid(form)


class SemesterUpdateView(AcademicManagementRoleMixin, UpdateView):
    model = Semester
    form_class = SemesterForm
    template_name = 'academics/semester_form.html'
    success_url = reverse_lazy('academics:semester_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Semester "{form.instance}" updated.')
        return super().form_valid(form)


class SemesterArchiveToggleView(AcademicManagementRoleMixin, View):
    def post(self, request, pk):
        semester = get_object_or_404(Semester.all_objects, pk=pk)
        if semester.is_deleted:
            services.restore_semester(semester)
            messages.success(request, f'Semester "{semester}" restored.')
        else:
            services.archive_semester(semester)
            messages.success(request, f'Semester "{semester}" archived.')
        return redirect('academics:semester_list')


class LevelSemesterStateView(AcademicManagementRoleMixin, FormView):
    """FR-REG-02, per level: each student level runs its own current
    semester (Level 100 can be in First Semester while Level 200 is in
    Second), so the Registrar sets every level's semester here instead
    of activating one semester globally.
    """
    form_class = LevelSemesterStateForm
    template_name = 'academics/level_states.html'
    success_url = reverse_lazy('academics:level_states')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_states = list(selectors.get_level_semester_states())
        # The table's per-level rows are the college-wide defaults (no
        # programme); programme-specific overrides are listed separately.
        states_by_level = {state.level: state for state in all_states if state.programme_id is None}
        context['programme_states'] = [state for state in all_states if state.programme_id]
        context['level_rows'] = [
            {'level': value, 'label': label, 'state': states_by_level.get(value)}
            for value, label in Level.choices
        ]
        context['semesters'] = Semester.objects.select_related('session')
        context['programmes'] = selectors.get_active_programmes()
        context['selection_form'] = kwargs.get('selection_form') or LevelSemesterSelectionForm()
        return context

    def post(self, request, *args, **kwargs):
        removing = request.POST.get('remove_programme_state')
        if removing:
            state = LevelSemesterState.objects.filter(pk=removing, programme__isnull=False).first()                 if _is_uuid(removing) else None
            if state:
                services.clear_level_semester(state.level, programme=state.programme)
                messages.success(request, f'{state.programme} / {state.get_level_display()} now follows the default.')
            return redirect(self.success_url)
        # The Program -> Level -> Semester-Session selector posts a
        # "programme" field; the per-row table forms don't.
        if 'programme' in request.POST:
            form = LevelSemesterSelectionForm(request.POST)
            if form.is_valid():
                level = form.cleaned_data['level']
                semester = form.cleaned_data['semester']
                programme = form.cleaned_data['programme']
                services.set_level_semester(level, semester, programme=programme)
                messages.success(
                    request,
                    f'{dict(Level.choices)[level]} ({programme}) is now in {semester}.',
                )
                return redirect(self.success_url)
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        level = form.cleaned_data['level']
        semester = form.cleaned_data['semester']
        level_label = dict(form.fields['level'].choices)[level]
        if semester:
            services.set_level_semester(level, semester)
            messages.success(self.request, f'{level_label} is now in {semester}.')
        else:
            services.clear_level_semester(level)
            messages.success(self.request, f'{level_label} now has no semester in progress.')
        return redirect(self.success_url)


def _is_uuid(raw):
    import uuid
    try:
        uuid.UUID(str(raw))
        return True
    except ValueError:
        return False


def _get_programme(raw_id):
    try:
        return selectors.get_active_programmes().filter(pk=raw_id).first() if raw_id else None
    except (ValueError, ValidationError):
        return None


class ProgrammeLevelOptionsView(AcademicManagementRoleMixin, View):
    """JSON: the levels a programme spans, for the cascading selector."""

    def get(self, request):
        programme = _get_programme(request.GET.get('programme'))
        if programme is None:
            return JsonResponse({'levels': []})
        levels = [{'value': v, 'label': label} for v, label in selectors.get_levels_for_programme(programme)]
        return JsonResponse({'levels': levels})


class ProgrammeLevelSemesterOptionsView(AcademicManagementRoleMixin, View):
    """JSON: the Semester-Session combinations for a programme + level.
    Empty when the programme/level pair is invalid."""

    def get(self, request):
        programme = _get_programme(request.GET.get('programme'))
        level = request.GET.get('level', '')
        if programme is None or not level.isdigit() or int(level) not in programme.levels:
            return JsonResponse({'semesters': []})
        semesters = [
            {'value': str(s.pk), 'label': str(s)}
            for s in selectors.get_semesters_for_selection()
        ]
        return JsonResponse({'semesters': semesters})


class SemesterRegistrationWindowView(AcademicManagementRoleMixin, FormView):
    """FR-REG-03: set/modify registration deadlines for a semester. Each
    semester has its own window since different levels can be running
    different semesters at the same time.
    """
    form_class = RegistrationWindowForm
    template_name = 'academics/registration_window.html'
    success_url = reverse_lazy('academics:semester_list')

    def dispatch(self, request, *args, **kwargs):
        self.semester = get_object_or_404(Semester, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            'registration_start': self.semester.registration_start,
            'registration_end': self.semester.registration_end,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['semester'] = self.semester
        return context

    def form_valid(self, form):
        services.set_registration_window(
            self.semester,
            start=form.cleaned_data['registration_start'],
            end=form.cleaned_data['registration_end'],
        )
        messages.success(self.request, f'Registration window updated for {self.semester}.')
        return redirect(self.success_url)
