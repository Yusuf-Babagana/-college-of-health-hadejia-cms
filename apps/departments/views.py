from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin

from . import selectors, services
from .forms import AssignHODForm, DepartmentForm
from .models import Department


class DepartmentManagementRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.ICT_ADMIN, Role.SUPER_ADMIN)


class DepartmentListView(DepartmentManagementRoleMixin, PaginatedListMixin, ListView):
    template_name = 'departments/department_list.html'
    context_object_name = 'departments'

    def get_queryset(self):
        return selectors.get_department_list(
            search=self.request.GET.get('q'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class DepartmentCreateView(DepartmentManagementRoleMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'departments/department_form.html'
    success_url = reverse_lazy('departments:department_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Department'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Department "{form.instance.name}" created.')
        return super().form_valid(form)


class DepartmentUpdateView(DepartmentManagementRoleMixin, UpdateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'departments/department_form.html'
    success_url = reverse_lazy('departments:department_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object.name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Department "{form.instance.name}" updated.')
        return super().form_valid(form)


class DepartmentArchiveToggleView(DepartmentManagementRoleMixin, View):
    def post(self, request, pk):
        department = get_object_or_404(Department.all_objects, pk=pk)
        if department.is_deleted:
            services.restore_department(department)
            messages.success(request, f'Department "{department.name}" restored.')
        else:
            services.archive_department(department)
            messages.success(request, f'Department "{department.name}" archived.')
        return redirect('departments:department_list')


class AssignHODView(DepartmentManagementRoleMixin, FormView):
    form_class = AssignHODForm
    template_name = 'departments/assign_hod.html'

    def dispatch(self, request, *args, **kwargs):
        self.department = get_object_or_404(Department, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['department'] = self.department
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['department'] = self.department
        return context

    def get_success_url(self):
        return reverse_lazy('departments:department_list')

    def form_valid(self, form):
        lecturer = form.cleaned_data['lecturer']
        try:
            if lecturer:
                services.assign_hod(self.department, lecturer)
                messages.success(self.request, f'{lecturer} is now Head of {self.department.name}.')
            else:
                services.remove_hod(self.department)
                messages.success(self.request, f'Head of Department removed for {self.department.name}.')
        except ValidationError as exc:
            messages.error(self.request, exc.message)
        return redirect(self.get_success_url())
