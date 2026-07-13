from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin
from apps.departments.selectors import get_active_departments

from . import selectors, services
from .forms import LecturerCreateForm, LecturerUpdateForm
from .models import Lecturer


class LecturerManagementRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.ICT_ADMIN, Role.SUPER_ADMIN)


class LecturerListView(LecturerManagementRoleMixin, PaginatedListMixin, ListView):
    template_name = 'lecturers/lecturer_list.html'
    context_object_name = 'lecturers'

    def get_queryset(self):
        return selectors.get_lecturer_list(
            search=self.request.GET.get('q'),
            department=self.request.GET.get('department'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['departments'] = get_active_departments()
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class LecturerCreateView(LecturerManagementRoleMixin, FormView):
    form_class = LecturerCreateForm
    template_name = 'lecturers/lecturer_form.html'
    success_url = reverse_lazy('lecturers:lecturer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Lecturer Profile'
        return context

    def form_valid(self, form):
        try:
            lecturer = services.create_lecturer_profile(**form.cleaned_data)
        except ValidationError as exc:
            for field, errors in exc.message_dict.items():
                for error in errors:
                    form.add_error(field if field in form.fields else None, error)
            return self.form_invalid(form)
        messages.success(self.request, f'Lecturer profile created for {lecturer.user.get_full_name()}.')
        return redirect(self.success_url)


class LecturerUpdateView(LecturerManagementRoleMixin, UpdateView):
    model = Lecturer
    form_class = LecturerUpdateForm
    template_name = 'lecturers/lecturer_form.html'
    success_url = reverse_lazy('lecturers:lecturer_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Lecturer profile for {self.object.user.get_full_name()} updated.')
        return super().form_valid(form)


class LecturerArchiveToggleView(LecturerManagementRoleMixin, View):
    def post(self, request, pk):
        lecturer = get_object_or_404(Lecturer.all_objects, pk=pk)
        if lecturer.is_deleted:
            services.restore_lecturer(lecturer)
            messages.success(request, f'Lecturer profile for {lecturer.user.get_full_name()} restored.')
        else:
            services.archive_lecturer(lecturer)
            messages.success(request, f'Lecturer profile for {lecturer.user.get_full_name()} archived.')
        return redirect('lecturers:lecturer_list')
