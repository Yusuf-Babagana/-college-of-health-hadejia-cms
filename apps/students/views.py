from django.contrib import messages
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import FormView, ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin
from apps.departments.selectors import get_active_departments

from . import selectors, services
from .forms import (
    BulkPromotionForm,
    GuardianForm,
    StudentAccountForm,
    StudentCreateForm,
    StudentPersonalForm,
    StudentProfileForm,
    StudentStatusForm,
)
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
    """Add a student: account + profile in one step, matric number typed
    in by the Registrar (no fixed format, no auto-generation). Available
    to ICT Admin and Registrar alike.
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


class MyStudentProfileView(RoleRequiredMixin, View):
    """The student's own personal profile: contact + profile picture,
    personal details and guardian, saved together. Academic fields
    (matric number, department, level, status) stay with the Registrar.
    """
    allowed_roles = (Role.STUDENT,)
    template_name = 'students/my_profile.html'

    def _student(self, request):
        return getattr(request.user, 'student_profile', None)

    def _forms(self, student, data=None, files=None):
        return {
            'account_form': StudentAccountForm(data, files, instance=student.user, prefix='account'),
            'personal_form': StudentPersonalForm(data, instance=student, prefix='personal'),
            'guardian_form': GuardianForm(data, instance=getattr(student, 'guardian', None), prefix='guardian'),
        }

    def _render(self, request, student, forms):
        from django.shortcuts import render

        return render(request, self.template_name, {
            **forms, 'student': student, 'completeness': selectors.get_profile_completeness(student),
        })

    def get(self, request):
        student = self._student(request)
        if student is None:
            messages.error(request, 'No student profile is linked to your account. Contact the Registrar.')
            return redirect('dashboard:redirect')
        return self._render(request, student, self._forms(student))

    def post(self, request):
        student = self._student(request)
        if student is None:
            return redirect('dashboard:redirect')
        forms = self._forms(student, request.POST, request.FILES)
        if not all(form.is_valid() for form in forms.values()):
            messages.error(request, 'Please correct the highlighted fields.')
            return self._render(request, student, forms)

        try:
            with transaction.atomic():
                forms['account_form'].save()
                forms['personal_form'].save()
                guardian = forms['guardian_form'].save(commit=False)
                guardian.student = student
                guardian.save()
                photo = forms['account_form'].cleaned_data.get('photo')
                if photo:
                    services.update_profile_photo(request.user, photo)
        except ValidationError as exc:
            forms['account_form'].add_error('photo', exc)
            return self._render(request, student, forms)

        messages.success(request, 'Your profile has been saved.')
        return redirect('students:my_profile')


class StudentPromoteView(StudentManagementRoleMixin, View):
    """Promote a student to the next level. POST-only; reports the level
    actually stored after saving."""

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        old_level = student.get_level_display()
        try:
            services.promote_student(student)
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        else:
            messages.success(
                request,
                f'{student.matric_number} promoted from {old_level} to {student.get_level_display()}.',
            )
        next_url = request.POST.get('next', '')
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse('students:student_list')
        return redirect(next_url)


class StudentBulkPromoteView(RoleRequiredMixin, FormView):
    """Super Admin only: promote a whole level (or one programme's level)
    in one go. Two steps - choose, then see the counts and confirm - so a
    mass promotion is never one accidental click."""
    allowed_roles = (Role.SUPER_ADMIN,)
    form_class = BulkPromotionForm
    template_name = 'students/bulk_promote.html'
    success_url = reverse_lazy('dashboard:redirect')

    def form_valid(self, form):
        level, programme = form.cleaned_data['level'], form.cleaned_data['programme']
        if self.request.POST.get('confirm') != '1':
            will_promote, at_final = services.preview_bulk_promotion(level=level, programme=programme)
            return self.render_to_response(self.get_context_data(
                form=form, preview={
                    'level': level, 'level_label': dict(form.fields['level'].choices)[level],
                    'next_label': self._next_label(level, programme),
                    'programme': programme, 'will_promote': will_promote, 'at_final': at_final,
                },
            ))
        promoted, skipped = services.promote_students(level=level, programme=programme)
        scope = f'{programme} ' if programme else ''
        messages.success(
            self.request,
            f'Promoted {promoted} {scope}student(s) from {dict(form.fields["level"].choices)[level]}.'
            + (f' {skipped} at their final level were left unchanged - mark them Graduated.' if skipped else ''),
        )
        return redirect(self.success_url)

    @staticmethod
    def _next_label(level, programme):
        from apps.core.constants import Level

        labels = dict(Level.choices)
        levels = programme.levels if programme else [value for value, _ in Level.choices]
        higher = [value for value in levels if value > level]
        return labels[min(higher)] if higher else None


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
