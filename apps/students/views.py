from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin
from apps.departments.selectors import get_active_departments

from . import selectors, services
from .forms import StudentCreateForm, StudentProfileForm, StudentStatusForm
from .models import Student


class StudentManagementRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.REGISTRAR, Role.ICT_ADMIN, Role.SUPER_ADMIN)


class StudentListView(StudentManagementRoleMixin, PaginatedListMixin, ListView):
    """FR-REG-06: searchable, filterable master student directory."""
    template_name = 'students/student_list.html'
    context_object_name = 'students'

    def get_queryset(self):
        return selectors.get_student_list(
            search=self.request.GET.get('q'),
            department=self.request.GET.get('department'),
            level=self.request.GET.get('level'),
            status=self.request.GET.get('status'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['departments'] = get_active_departments()
        context['level_choices'] = Student._meta.get_field('level').choices
        context['status_choices'] = Student.Status.choices
        context['search_query'] = self.request.GET.get('q', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_level'] = self.request.GET.get('level', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class StudentCreateView(StudentManagementRoleMixin, FormView):
    """Add a student: account + profile in one step, matric number
    auto-generated. Available to ICT Admin and Registrar alike.
    """
    form_class = StudentCreateForm
    template_name = 'students/student_form.html'
    success_url = reverse_lazy('students:student_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Student'
        return context

    def form_valid(self, form):
        try:
            student, temp_password = services.create_student(**form.cleaned_data)
        except ValidationError as exc:
            for field, errors in exc.message_dict.items():
                for error in errors:
                    form.add_error(field if field in form.fields else None, error)
            return self.form_invalid(form)

        messages.success(
            self.request,
            f'Student "{student.matric_number}" created. '
            f'Username: {student.user.username} — Temporary password: {temp_password} '
            '(shown once - share it securely; they must change it on first login).',
        )
        return redirect(self.success_url)


class StudentProfileUpdateView(StudentManagementRoleMixin, UpdateView):
    model = Student
    form_class = StudentProfileForm
    template_name = 'students/student_form.html'
    success_url = reverse_lazy('students:student_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object.matric_number}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Student "{self.object.matric_number}" updated.')
        return super().form_valid(form)


class StudentStatusUpdateView(StudentManagementRoleMixin, View):
    """FR-REG-05: change a student's academic status."""

    def get(self, request, pk):
        from django.shortcuts import render

        student = get_object_or_404(Student, pk=pk)
        form = StudentStatusForm(initial={'status': student.status})
        return render(request, 'students/student_status_form.html', {'student': student, 'form': form})

    def post(self, request, pk):
        from django.shortcuts import render

        student = get_object_or_404(Student, pk=pk)
        form = StudentStatusForm(request.POST)
        if form.is_valid():
            services.update_student_status(student, form.cleaned_data['status'])
            messages.success(
                request,
                f'Status for "{student.matric_number}" updated to {student.get_status_display()}.',
            )
            return redirect('students:student_list')
        return render(request, 'students/student_status_form.html', {'student': student, 'form': form})


class StudentArchiveToggleView(StudentManagementRoleMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(Student.all_objects, pk=pk)
        if student.is_deleted:
            services.restore_student(student)
            messages.success(request, f'Student "{student.matric_number}" restored.')
        else:
            services.archive_student(student)
            messages.success(request, f'Student "{student.matric_number}" archived.')
        return redirect('students:student_list')


class DepartmentStudentListView(RoleRequiredMixin, PaginatedListMixin, ListView):
    """FR-HOD-01: a read-only directory of students in the HOD's own
    department - editing status/archiving remains the Registrar's job
    via StudentListView above.
    """
    allowed_roles = (Role.HOD,)
    template_name = 'students/department_student_list.html'
    context_object_name = 'students'

    def get_department(self):
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        return lecturer_profile.department if lecturer_profile else None

    def get_queryset(self):
        department = self.get_department()
        if not department:
            return Student.objects.none()
        return selectors.get_student_list(
            department=department.pk,
            search=self.request.GET.get('q'),
            level=self.request.GET.get('level'),
            status=self.request.GET.get('status'),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['department'] = self.get_department()
        context['level_choices'] = Student._meta.get_field('level').choices
        context['status_choices'] = Student.Status.choices
        context['search_query'] = self.request.GET.get('q', '')
        context['current_level'] = self.request.GET.get('level', '')
        context['current_status'] = self.request.GET.get('status', '')
        return context
