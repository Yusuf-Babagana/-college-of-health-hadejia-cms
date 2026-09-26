from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin
from apps.core.utils.pdf import render_to_pdf_response
from apps.departments.selectors import get_active_departments

from . import selectors, services
from .forms import CourseForm, CourseOfferingForm
from .models import Course, CourseOffering, CourseRegistration, RegistrationApproval


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


class CourseAllocationView(HODCourseOfferingMixin, TemplateView):
    """FR: course allocation browsed Programme -> Level -> Semester ->
    Courses, rather than picking a course out of one flat list - each
    course shows its already-assigned lecturer (Manage) or an Assign
    button that jumps to Assign Course with the course pre-selected.
    Super Admin picks a department first, same as the other oversight
    screens, since their account isn't tied to one department.
    """
    template_name = 'courses/course_allocation.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department = self.get_department()
        is_overseer = self.is_overseer()
        context['is_overseer'] = is_overseer

        if is_overseer:
            context['departments'] = get_active_departments()
            department_id = self.request.GET.get('department')
            context['current_department'] = department_id or ''
            department = get_active_departments().filter(pk=department_id).first() if department_id else None

        context['department'] = department
        if department:
            current_offerings = selectors.get_current_offerings_for_department(department)
            context['course_tree'] = selectors.get_department_course_tree(
                department, current_offerings_by_key=current_offerings,
            )
        return context


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

    def get_initial(self):
        # Pre-select the course when arriving from the Allocate Courses
        # tree ("Assign" on a specific course) instead of the plain
        # "Assign Course" link, which starts blank.
        initial = super().get_initial()
        course_id = self.request.GET.get('course')
        if course_id:
            initial['course'] = course_id
        return initial

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

        # The "Manage Registration" screen reuses this same cancel action
        # for its own Drop buttons and wants to land back on itself
        # rather than the flat department-wide list.
        if request.POST.get('return_to') == 'manage':
            return redirect(
                'courses:manage_student_registration',
                student_pk=registration.student_id,
                semester_pk=registration.course_offering.semester_id,
            )
        return redirect('courses:department_registrations')


class RegistrationApprovalQueueView(HODCourseOfferingMixin, TemplateView):
    """FR-HOD-07: one row per student+semester with active registrations
    in the HOD's department - approve the whole registration at once, or
    jump into "Manage" to add/drop courses on the student's behalf.
    """
    template_name = 'courses/registration_approval_queue.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department = self.get_department()
        context['department'] = department
        context['is_overseer'] = self.is_overseer()

        if self.is_overseer():
            context['departments'] = get_active_departments()
            department_id = self.request.GET.get('department')
            context['current_department'] = department_id or ''
            department = get_active_departments().filter(pk=department_id).first() if department_id else None

        if not department and not self.is_overseer():
            context['rows'] = []
        else:
            context['rows'] = selectors.get_registration_approval_queue(department)
        return context


class HODStudentRegistrationMixin(HODCourseOfferingMixin):
    """Shared student/semester lookup for the HOD approve/manage screens,
    scoped to the HOD's own department the same way every other HOD
    oversight screen is - via Student.department, never Programme, since
    Programme.department is unreliable (see get_department_course_tree).
    """

    def get_student_or_404(self, pk):
        from apps.students.models import Student

        department = self.get_department()
        if department:
            return get_object_or_404(Student, pk=pk, department=department)
        if self.is_overseer():
            return get_object_or_404(Student, pk=pk)
        raise Http404

    def get_semester_or_404(self, pk):
        from apps.academics.models import Semester

        return get_object_or_404(Semester, pk=pk)


class ApproveRegistrationView(HODStudentRegistrationMixin, View):
    def post(self, request, student_pk, semester_pk):
        student = self.get_student_or_404(student_pk)
        semester = self.get_semester_or_404(semester_pk)
        try:
            services.approve_registration(student=student, semester=semester, reviewer=request.user)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Approved {student.matric_number}\'s registration for {semester}.')

        if request.POST.get('return_to') == 'manage':
            return redirect('courses:manage_student_registration', student_pk=student.pk, semester_pk=semester.pk)
        return redirect('courses:registration_approvals')


class UnapproveRegistrationView(HODStudentRegistrationMixin, View):
    def post(self, request, student_pk, semester_pk):
        student = self.get_student_or_404(student_pk)
        semester = self.get_semester_or_404(semester_pk)
        try:
            services.unapprove_registration(student=student, semester=semester, reviewer=request.user)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(
                request, f'Reopened {student.matric_number}\'s registration for {semester} for self-service editing.',
            )
        return redirect('courses:manage_student_registration', student_pk=student.pk, semester_pk=semester.pk)


class ManageStudentRegistrationView(HODStudentRegistrationMixin, TemplateView):
    """FR-HOD-07: once a student's registration is approved (or the
    registration window has closed), this is where their add/drop
    requests get actioned - by the HOD, not the student's own dashboard.
    """
    template_name = 'courses/manage_student_registration.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.get_student_or_404(kwargs['student_pk'])
        semester = self.get_semester_or_404(kwargs['semester_pk'])

        context['student'] = student
        context['semester'] = semester
        context['registrations'] = selectors.get_registered_courses(student, semester=semester)
        context['total_units'] = sum(
            reg.course_offering.course.credit_units for reg in context['registrations']
        )
        context['approval'] = selectors.get_registration_approval(student, semester)
        context['is_approved'] = selectors.is_registration_approved(student, semester)
        context['available_offerings'] = selectors.get_available_offerings_for_student(student, semester)
        return context


class HODAddCourseView(HODStudentRegistrationMixin, View):
    def post(self, request, student_pk):
        student = self.get_student_or_404(student_pk)
        offering = get_object_or_404(CourseOffering, pk=request.POST.get('course_offering'))
        try:
            services.hod_register_course(student=student, course_offering=offering)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Registered {student.matric_number} for {offering.course.code}.')
        return redirect('courses:manage_student_registration', student_pk=student.pk, semester_pk=offering.semester_id)


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
        if self.student_profile:
            # FR-STU-CARRY: a failed course re-registers itself the
            # moment it's re-offered - runs here so it happens as a
            # normal side effect of visiting the registration screens,
            # not something the student has to remember to trigger.
            services.sync_carryover_registrations(self.student_profile)
        self.active_semester = (
            get_semester_for_level(self.student_profile.level) if self.student_profile else None
        )
        self.is_cleared = None

        if not self.student_profile or not self.active_semester:
            return CourseOffering.objects.none()

        self.is_cleared = is_student_cleared(self.student_profile, self.active_semester.session)
        if not self.is_cleared:
            return CourseOffering.objects.none()

        # FR-HOD-07: once the HOD has approved this semester's
        # registration, self-service add locks - further courses have to
        # go through the HOD dashboard instead.
        if selectors.is_registration_approved(self.student_profile, self.active_semester):
            return CourseOffering.objects.none()

        return selectors.get_available_offerings_for_student(self.student_profile, self.active_semester)

    def get_context_data(self, **kwargs):
        from apps.core.constants import MAX_CREDIT_UNITS_PER_SEMESTER

        context = super().get_context_data(**kwargs)
        context['student_profile'] = self.student_profile
        context['is_approved'] = bool(
            self.student_profile and self.active_semester
            and selectors.is_registration_approved(self.student_profile, self.active_semester)
        )
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
        if student_profile:
            services.sync_carryover_registrations(student_profile)
        self.active_semester = get_semester_for_level(student_profile.level) if student_profile else None
        if not student_profile or not self.active_semester:
            return CourseOffering.objects.none()
        return selectors.get_registered_courses(student_profile, semester=self.active_semester)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student_profile = getattr(self.request.user, 'student_profile', None)
        context['student_profile'] = student_profile
        context['active_semester'] = self.active_semester
        context['total_units'] = sum(
            reg.course_offering.course.credit_units for reg in context[self.context_object_name]
        )
        # FR-HOD-07: printing locks IN, not out - the slip only becomes
        # available once the HOD has approved, and dropping locks OUT the
        # moment they do, since further changes route through the HOD.
        context['is_approved'] = bool(
            student_profile and self.active_semester
            and selectors.is_registration_approved(student_profile, self.active_semester)
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
        if not active_semester or not selectors.is_registration_approved(student_profile, active_semester):
            messages.error(
                request,
                'Your registration slip is only available once your HOD has approved your course registration.',
            )
            return redirect('courses:my_registrations')

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


class MyCarryoverView(StudentCourseRoleMixin, TemplateView):
    """FR-STU-CARRY: every course the student's most recent published
    result was a Fail in, and whether it's currently registered for a
    retake. Visiting this page (like the registration screens) triggers
    sync_carryover_registrations, so a freshly re-offered fail course
    registers itself right here too, not only from Available Courses.
    """
    template_name = 'courses/my_carryover.html'

    def get_context_data(self, **kwargs):
        from apps.results.selectors import get_carryover_courses

        context = super().get_context_data(**kwargs)
        student_profile = getattr(self.request.user, 'student_profile', None)
        context['student_profile'] = student_profile
        if not student_profile:
            context['rows'] = []
            return context

        services.sync_carryover_registrations(student_profile)

        rows = []
        for entry in get_carryover_courses(student_profile):
            course = entry['course']
            current_offering = selectors.get_current_offering_for_course(course)
            has_fresh_offering = bool(current_offering and current_offering.pk != entry['failed_offering'].pk)
            is_registered = bool(
                has_fresh_offering
                and CourseRegistration.objects.filter(
                    student=student_profile, course_offering=current_offering,
                    status=CourseRegistration.Status.REGISTERED,
                ).exists()
            )
            rows.append({
                'course': course,
                'failed_grade': entry['failed_grade'],
                'failed_offering': entry['failed_offering'],
                'current_offering': current_offering if has_fresh_offering else None,
                'is_registered': is_registered,
            })
        context['rows'] = rows
        return context


class RegistrationConflictsView(RoleRequiredMixin, TemplateView):
    """Diagnostic report: students registered under courses from more
    than one Programme - see get_cross_programme_registration_conflicts.
    Read-only; actually dropping the wrong registration happens on the
    existing Course Registration Oversight screen (or Django admin), not
    here, since there's no way to know automatically which registration
    is the mistake.
    """
    template_name = 'courses/registration_conflicts.html'
    allowed_roles = (Role.EXAM_OFFICER, Role.REGISTRAR, Role.HOD, Role.SUPER_ADMIN)

    def get_department(self):
        if self.request.user.role != Role.HOD:
            return None
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        return lecturer_profile.department if lecturer_profile else None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        is_hod = self.request.user.role == Role.HOD
        context['is_hod'] = is_hod

        if is_hod:
            department = self.get_department()
            context['department'] = department
        else:
            department_id = self.request.GET.get('department')
            department = get_active_departments().filter(pk=department_id).first() if department_id else None
            context['departments'] = get_active_departments()
            context['current_department'] = department_id or ''
            context['department'] = department

        if is_hod and not department:
            context['conflicts'] = []
        else:
            context['conflicts'] = selectors.get_cross_programme_registration_conflicts(department=department)

        return context
