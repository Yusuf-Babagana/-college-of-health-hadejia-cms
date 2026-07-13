from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin

from . import selectors, services
from .forms import (
    AcademicSessionForm,
    LevelSemesterStateForm,
    RegistrationWindowForm,
    SemesterForm,
)
from .models import AcademicSession, Semester


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
        from apps.core.constants import Level

        context = super().get_context_data(**kwargs)
        states_by_level = {state.level: state for state in selectors.get_level_semester_states()}
        context['level_rows'] = [
            {'level': value, 'label': label, 'state': states_by_level.get(value)}
            for value, label in Level.choices
        ]
        context['semesters'] = Semester.objects.select_related('session')
        return context

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
