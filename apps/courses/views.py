from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin
from apps.core.utils.pdf import render_to_pdf_response
from apps.departments.selectors import get_active_departments

from . import selectors, services
from .forms import CourseForm, CourseOfferingForm
from .models import Course, CourseOffering, CourseRegistration


class CourseManagementRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.ICT_ADMIN, Role.SUPER_ADMIN)


class CourseListView(CourseManagementRoleMixin, PaginatedListMixin, ListView):
    template_name = 'courses/course_list.html'
    context_object_name = 'courses'

    def get_queryset(self):
        return selectors.get_course_list(
            search=self.request.GET.get('q'),
            department=self.request.GET.get('department'),
            level=self.request.GET.get('level'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_level'] = self.request.GET.get('level', '')
        context['departments'] = get_active_departments()
        context['level_choices'] = Course._meta.get_field('level').choices
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class CourseCreateView(CourseManagementRoleMixin, CreateView):
    model = Course
    form_class = CourseForm
    template_name = 'courses/course_form.html'
    success_url = reverse_lazy('courses:course_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Course'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Course "{form.instance.code}" created.')
        return super().form_valid(form)


class CourseUpdateView(CourseManagementRoleMixin, UpdateView):
    model = Course
    form_class = CourseForm
    template_name = 'courses/course_form.html'
    success_url = reverse_lazy('courses:course_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object.code}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Course "{form.instance.code}" updated.')
        return super().form_valid(form)


class CourseArchiveToggleView(CourseManagementRoleMixin, View):
    def post(self, request, pk):
        course = get_object_or_404(Course.all_objects, pk=pk)
        if course.is_deleted:
            services.restore_course(course)
            messages.success(request, f'Course "{course.code}" restored.')
        else:
            services.archive_course(course)
            messages.success(request, f'Course "{course.code}" archived.')
        return redirect('courses:course_list')


class HODCourseOfferingMixin(RoleRequiredMixin):
    """FR: HOD 'Assign Courses' - scoped to the HOD's own department.
    Super Admin gets cross-department oversight instead of a department
    scope, since their account isn't tied to a single Lecturer profile.
    """
    allowed_roles = (Role.HOD, Role.SUPER_ADMIN)

    def get_department(self):
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        return lecturer_profile.department if lecturer_profile else None

    def is_overseer(self):
        return self.request.user.role == Role.SUPER_ADMIN


class CourseOfferingListView(HODCourseOfferingMixin, PaginatedListMixin, ListView):
    template_name = 'courses/course_offering_list.html'
    context_object_name = 'offerings'

    def get_queryset(self):
        department = self.get_department()
        if not department and not self.is_overseer():
            return CourseOffering.objects.none()

        filter_department = department or self.request.GET.get('department')
        return selectors.get_offerings_for_department(
            filter_department,
            semester=self.request.GET.get('semester'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        from apps.academics.models import Semester
        from apps.departments.selectors import get_active_departments

        context = super().get_context_data(**kwargs)
        context['department'] = self.get_department()
        context['is_overseer'] = self.is_overseer()
        if self.is_overseer():
            context['departments'] = get_active_departments()
            context['current_department'] = self.request.GET.get('department', '')
        context['semesters'] = Semester.objects.select_related('session')
        context['current_semester'] = self.request.GET.get('semester', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class CourseOfferingCreateView(HODCourseOfferingMixin, CreateView):
    """FR-HOD-02: activates a catalog course as a Course Offering for
    the semester its level is currently running - never a semester of
    the HOD's choosing. The form resolves it from the selected course.
    """
    model = CourseOffering
    form_class = CourseOfferingForm
    template_name = 'courses/course_offering_form.html'
    success_url = reverse_lazy('courses:course_offering_list')

    def dispatch(self, request, *args, **kwargs):
        from apps.academics.selectors import get_level_semester_states

        if not get_level_semester_states().exists():
            messages.error(
                request,
                'No level has a semester in progress. Ask the Registrar to set the '
                'current semester for each level before assigning courses.',
            )
            return redirect('courses:course_offering_list')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['department'] = self.get_department()
        return kwargs

    def get_context_data(self, **kwargs):
        from apps.academics.selectors import get_level_semester_states

        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Assign Course'
        context['level_states'] = get_level_semester_states()
        return context

    def form_valid(self, form):
        messages.success(self.request, f'"{form.instance.course}" assigned for {form.instance.semester}.')
        return super().form_valid(form)


class CourseOfferingUpdateView(HODCourseOfferingMixin, UpdateView):
    model = CourseOffering
    form_class = CourseOfferingForm
    template_name = 'courses/course_offering_form.html'
    success_url = reverse_lazy('courses:course_offering_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['department'] = self.get_department()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object}'
        context['locked_semester'] = self.object.semester
        return context

    def form_valid(self, form):
        messages.success(self.request, f'"{form.instance}" updated.')
        return super().form_valid(form)


class CourseOfferingArchiveToggleView(HODCourseOfferingMixin, View):
    def post(self, request, pk):
        offering = get_object_or_404(CourseOffering.all_objects, pk=pk)
        if offering.is_deleted:
            services.restore_course_offering(offering)
            messages.success(request, f'"{offering}" restored.')
        else:
            services.archive_course_offering(offering)
            messages.success(request, f'"{offering}" archived.')
        return redirect('courses:course_offering_list')


class DepartmentRegistrationListView(HODCourseOfferingMixin, PaginatedListMixin, ListView):
    """FR-HOD-06: registration oversight - every student registered for
    a course in the HOD's department, with the option to cancel one.
    """
    template_name = 'courses/department_registration_list.html'
    context_object_name = 'registrations'

    def get_queryset(self):
        department = self.get_department()
        if not department and not self.is_overseer():
            return CourseRegistration.objects.none()

        filter_department = department or self.request.GET.get('department')
        return selectors.get_registrations_for_department(
            filter_department,
            semester=self.request.GET.get('semester'),
            status=self.request.GET.get('status'),
        )

    def get_context_data(self, **kwargs):
        from apps.academics.models import Semester

        context = super().get_context_data(**kwargs)
        context['department'] = self.get_department()
        context['is_overseer'] = self.is_overseer()
        if self.is_overseer():
            context['departments'] = get_active_departments()
            context['current_department'] = self.request.GET.get('department', '')
        context['semesters'] = Semester.objects.select_related('session')
        context['current_semester'] = self.request.GET.get('semester', '')
        context['status_choices'] = CourseRegistration.Status.choices
        context['current_status'] = self.request.GET.get('status', '')
        return context


class HODCancelRegistrationView(HODCourseOfferingMixin, View):
    def post(self, request, pk):
        department = self.get_department()
        if department:
            registration = get_object_or_404(
                CourseRegistration, pk=pk, course_offering__course__department=department,
            )
        elif self.is_overseer():
            registration = get_object_or_404(CourseRegistration, pk=pk)
        else:
            raise Http404

        try:
            services.hod_cancel_registration(registration)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(
                request,
                f'Cancelled {registration.student.matric_number}\'s registration for '
                f'{registration.course_offering.course.code}.',
            )
        return redirect('courses:department_registrations')


class StudentCourseRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.STUDENT,)


class AvailableCourseListView(StudentCourseRoleMixin, ListView):
    """FR-STU-04/05: courses in the student's department and level open
    for registration this (active) semester. Financial clearance is
    enforced here at the page level - an uncleared student never even
    sees the course list, not just a rejected register click.
    """
    template_name = 'courses/available_courses.html'
    context_object_name = 'offerings'

    def get_queryset(self):
        from apps.academics.selectors import get_semester_for_level
        from apps.finance.selectors import is_student_cleared

        self.student_profile = getattr(self.request.user, 'student_profile', None)
        self.active_semester = (
            get_semester_for_level(self.student_profile.level) if self.student_profile else None
        )
        self.is_cleared = None

        if not self.student_profile or not self.active_semester:
            return CourseOffering.objects.none()

        self.is_cleared = is_student_cleared(self.student_profile, self.active_semester.session)
        if not self.is_cleared:
            return CourseOffering.objects.none()

        return selectors.get_available_offerings_for_student(self.student_profile, self.active_semester)

    def get_context_data(self, **kwargs):
        from apps.core.constants import MAX_CREDIT_UNITS_PER_SEMESTER

        context = super().get_context_data(**kwargs)
        context['student_profile'] = self.student_profile
        context['active_semester'] = self.active_semester
        context['is_cleared'] = self.is_cleared
        context['max_units'] = MAX_CREDIT_UNITS_PER_SEMESTER

        if self.student_profile and self.active_semester and self.is_cleared:
            context['current_units'] = sum(
                reg.course_offering.course.credit_units
                for reg in selectors.get_registered_courses(
                    self.student_profile, semester=self.active_semester,
                ).select_related('course_offering__course')
            )

        return context


class RegisterCourseView(StudentCourseRoleMixin, View):
    def post(self, request, pk):
        student_profile = getattr(request.user, 'student_profile', None)
        offering = get_object_or_404(CourseOffering, pk=pk)
        try:
            services.register_course(student=student_profile, course_offering=offering)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Registered for {offering.course.code}.')
        return redirect('courses:available_courses')


class MyCourseRegistrationsView(StudentCourseRoleMixin, ListView):
    """FR-STU-08: "My Schedule" - the student's finalized registrations
    for the CURRENT semester specifically, not every registration
    they've ever made (a past semester's dropped-but-never-cleared-out
    rows shouldn't show up as if they were part of this term).
    """
    template_name = 'courses/my_registrations.html'
    context_object_name = 'registrations'

    def get_queryset(self):
        from apps.academics.selectors import get_semester_for_level

        student_profile = getattr(self.request.user, 'student_profile', None)
        self.active_semester = get_semester_for_level(student_profile.level) if student_profile else None
        if not student_profile or not self.active_semester:
            return CourseOffering.objects.none()
        return selectors.get_registered_courses(student_profile, semester=self.active_semester)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['student_profile'] = getattr(self.request.user, 'student_profile', None)
        context['active_semester'] = self.active_semester
        context['total_units'] = sum(
            reg.course_offering.course.credit_units for reg in context[self.context_object_name]
        )
        return context


class DropCourseView(StudentCourseRoleMixin, View):
    def post(self, request, pk):
        student_profile = getattr(request.user, 'student_profile', None)
        offering = get_object_or_404(CourseOffering, pk=pk)
        try:
            services.drop_course(student=student_profile, course_offering=offering)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Dropped {offering.course.code}.')
        return redirect('courses:my_registrations')


class RegistrationSlipPDFView(StudentCourseRoleMixin, View):
    def get(self, request):
        student_profile = getattr(request.user, 'student_profile', None)
        if not student_profile:
            messages.error(request, 'No student profile linked to your account.')
            return redirect('courses:my_registrations')

        from apps.academics.selectors import get_semester_for_level

        active_semester = get_semester_for_level(student_profile.level)
        registrations = list(selectors.get_registered_courses(student_profile, semester=active_semester))
        total_units = sum(reg.course_offering.course.credit_units for reg in registrations)

        return render_to_pdf_response(
            'courses/registration_slip_pdf.html',
            {
                'student': student_profile,
                'semester': active_semester,
                'registrations': registrations,
                'total_units': total_units,
                'college_name': 'College of Health Sciences and Technology, Hadejia',
            },
            filename=f'registration-slip-{student_profile.matric_number}.pdf'.replace('/', '-'),
        )
