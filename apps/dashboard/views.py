from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.constants import ROLE_DASHBOARD_URL_NAMES, Role
from apps.core.mixins import RoleRequiredMixin


class DashboardRedirectView(LoginRequiredMixin, View):
    """Single entry point after login; sends the user to their role's
    dashboard so templates and URLs never need to guess the role.
    """

    def get(self, request):
        if request.user.is_superuser and not request.user.role:
            return redirect(reverse('admin:index'))

        url_name = ROLE_DASHBOARD_URL_NAMES.get(request.user.role)
        if not url_name:
            return redirect(reverse('admin:index'))
        return redirect(reverse(url_name))


class HomeView(TemplateView):
    """Public marketing homepage. Logged-in visitors are sent straight to
    their dashboard - the homepage is only for anonymous visitors deciding
    whether/how to log in.
    """
    template_name = 'pages/home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard:redirect')
        return super().get(request, *args, **kwargs)


class StudentDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/student.html'
    allowed_roles = (Role.STUDENT,)

    def get_context_data(self, **kwargs):
        from apps.academics.selectors import get_semester_for_level
        from apps.courses.selectors import get_registered_courses
        from apps.finance.selectors import get_outstanding_balance_for_student, is_student_cleared
        from apps.results.selectors import compute_cgpa

        context = super().get_context_data(**kwargs)
        student_profile = getattr(self.request.user, 'student_profile', None)
        context['student_profile'] = student_profile

        # The student's own current semester/session follow their level.
        active_semester = get_semester_for_level(student_profile.level) if student_profile else None
        current_session = active_semester.session if active_semester else None
        context['current_session'] = current_session
        context['active_semester'] = active_semester

        if student_profile:
            context['outstanding_fees'] = get_outstanding_balance_for_student(student_profile)
            context['registered_course_count'] = get_registered_courses(
                student_profile, semester=active_semester,
            ).count()
            context['cgpa'] = compute_cgpa(student_profile)
            if current_session:
                context['is_financially_cleared'] = is_student_cleared(student_profile, current_session)

        return context


class LecturerDashboardView(RoleRequiredMixin, TemplateView):
    """FR-LEC-01: the dashboard's workload figures reflect the semesters
    currently running (for any level), not every offering ever assigned.
    """
    template_name = 'dashboard/lecturer.html'
    allowed_roles = (Role.LECTURER,)

    def get_context_data(self, **kwargs):
        from django.db.models import Sum

        from apps.academics.selectors import get_current_semesters
        from apps.results.models import Grade

        context = super().get_context_data(**kwargs)
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        context['lecturer_profile'] = lecturer_profile

        current_semesters = get_current_semesters()
        context['current_semesters'] = current_semesters

        if lecturer_profile:
            offerings = lecturer_profile.course_offerings.filter(
                semester__in=current_semesters,
            ).select_related('course', 'semester', 'semester__session').order_by('course__code')

            context['assigned_offerings'] = offerings
            context['total_courses'] = offerings.count()
            context['total_students'] = sum(o.registered_count for o in offerings)
            context['total_units'] = offerings.aggregate(total=Sum('course__credit_units'))['total'] or 0
            context['pending_grade_entries'] = Grade.objects.filter(
                course_offering__lecturer=lecturer_profile,
                status__in=[Grade.Status.DRAFT, Grade.Status.REJECTED],
            ).count()

            department = lecturer_profile.department
            context['department'] = department
            context['hod'] = department.hod if department else None

        return context


class HODDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/hod.html'
    allowed_roles = (Role.HOD,)

    def get_context_data(self, **kwargs):
        from django.db.models import Sum

        from apps.academics.selectors import get_current_semesters, get_level_semester_states
        from apps.courses.models import CourseOffering
        from apps.students.selectors import get_student_list

        context = super().get_context_data(**kwargs)
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        context['lecturer_profile'] = lecturer_profile

        if lecturer_profile:
            department = lecturer_profile.department
            department_lecturers = list(
                department.lecturers.select_related('user').order_by('user__first_name', 'user__last_name')
            )
            department_courses = department.courses.order_by('code')
            department_students = get_student_list(department=department.pk)

            current_semesters = get_current_semesters()
            workload = {lecturer.id: {'count': 0, 'units': 0} for lecturer in department_lecturers}
            current_offerings = CourseOffering.objects.filter(
                lecturer__department=department, semester__in=current_semesters,
            ).select_related('course')
            for offering in current_offerings:
                entry = workload[offering.lecturer_id]
                entry['count'] += 1
                entry['units'] += offering.course.credit_units
            for lecturer in department_lecturers:
                lecturer.current_offering_count = workload[lecturer.id]['count']
                lecturer.current_units = workload[lecturer.id]['units']

            # FR: an HOD who is personally assigned to teach a course (via
            # Department's "Assign Courses" screen, same as any lecturer)
            # needs their own allocated offerings surfaced on their
            # dashboard - not just the department-wide catalog/oversight
            # views above. Uses the same lecturer_profile-scoped query as
            # apps.results.selectors.get_offerings_for_lecturer, so what's
            # shown here always matches what "My Courses" -> class list ->
            # grade entry (results app) actually lets them act on.
            my_offerings = CourseOffering.objects.filter(
                lecturer=lecturer_profile,
            ).select_related('course', 'semester', 'semester__session').order_by(
                '-semester__session__name', 'course__code',
            )

            context['department'] = department
            context['level_states'] = get_level_semester_states()
            context['department_lecturers'] = department_lecturers
            context['department_courses'] = department_courses
            context['department_students'] = department_students
            context['my_offerings'] = my_offerings
            context['total_lecturers'] = len(department_lecturers)
            context['total_courses'] = department_courses.count()
            context['total_students'] = department_students.count()
            context['total_my_offerings'] = my_offerings.count()
            context['total_credit_units'] = (
                department_courses.aggregate(total=Sum('credit_units'))['total'] or 0
            )

        return context


class RegistrarDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/registrar.html'
    allowed_roles = (Role.REGISTRAR,)

    def get_context_data(self, **kwargs):
        from apps.academics.selectors import get_current_session, get_level_semester_states
        from apps.departments.models import Department
        from apps.students.models import Student

        context = super().get_context_data(**kwargs)
        context['level_states'] = get_level_semester_states()
        context['current_session'] = get_current_session()
        context['total_departments'] = Department.objects.count()
        context['total_students'] = Student.objects.count()
        return context


class BursarDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/bursar.html'
    allowed_roles = (Role.BURSAR,)

    def get_context_data(self, **kwargs):
        from apps.academics.selectors import get_current_sessions, get_level_semester_states
        from apps.finance.models import FeeStructure, Invoice
        from apps.finance.selectors import (
            get_defaulters,
            get_financial_summary,
            get_financial_summary_by_fee_type,
        )

        context = super().get_context_data(**kwargs)
        # Levels can straddle a session boundary, so the money overview
        # covers every session currently in progress for some level.
        current_sessions = get_current_sessions()
        context['current_sessions'] = current_sessions
        context['level_states'] = get_level_semester_states()

        summary = get_financial_summary(sessions=current_sessions)
        context['total_fee_structures'] = FeeStructure.objects.count()
        context['total_invoices'] = summary['invoice_count']
        context['total_revenue'] = summary['collected']
        context['total_outstanding'] = summary['outstanding']
        context['total_defaulters'] = get_defaulters(sessions=current_sessions).count()
        context['fee_type_summary'] = get_financial_summary_by_fee_type(sessions=current_sessions)
        return context


class ExamOfficerDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/exam_officer.html'
    allowed_roles = (Role.EXAM_OFFICER,)

    def get_context_data(self, **kwargs):
        from apps.results.models import Grade

        context = super().get_context_data(**kwargs)
        context['pending_approval'] = Grade.objects.filter(status=Grade.Status.SUBMITTED).count()
        context['pending_publish'] = Grade.objects.filter(status=Grade.Status.APPROVED).count()
        context['published_count'] = Grade.objects.filter(status=Grade.Status.PUBLISHED).count()
        return context


class PracticalCoordinatorDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/practical_coordinator.html'
    allowed_roles = (Role.PRACTICAL_COORD,)

    def get_context_data(self, **kwargs):
        from apps.practicals.models import PracticalPlacement
        from apps.practicals.selectors import get_practical_fee_types

        context = super().get_context_data(**kwargs)
        placements = PracticalPlacement.objects.all()
        context['fee_types'] = get_practical_fee_types()
        context['total_placements'] = placements.count()
        context['incomplete_placements'] = sum(1 for p in placements if not p.is_complete)
        return context


class ICTAdminDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/ict_admin.html'
    allowed_roles = (Role.ICT_ADMIN,)

    def get_context_data(self, **kwargs):
        from apps.accounts.models import User
        from apps.courses.models import Course
        from apps.departments.models import Department
        from apps.lecturers.models import Lecturer
        from apps.students.models import Student

        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['total_departments'] = Department.objects.count()
        context['total_lecturers'] = Lecturer.objects.count()
        context['total_students'] = Student.objects.count()
        context['total_courses'] = Course.objects.count()
        return context


class SuperAdminDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'dashboard/super_admin.html'
    allowed_roles = (Role.SUPER_ADMIN,)

    def get_context_data(self, **kwargs):
        from django.db.models import Count

        from apps.academics.selectors import get_current_sessions, get_level_semester_states
        from apps.accounts.models import User
        from apps.courses.models import Course, CourseOffering
        from apps.departments.models import Department
        from apps.finance.selectors import get_defaulters, get_financial_summary
        from apps.results.models import Grade
        from apps.students.models import Student

        context = super().get_context_data(**kwargs)

        context['total_users'] = User.objects.count()
        context['total_students'] = Student.objects.count()
        context['total_staff'] = User.objects.exclude(role=Role.STUDENT).count()

        current_sessions = get_current_sessions()
        context['current_session'] = current_sessions.first()
        context['current_sessions'] = current_sessions
        context['level_states'] = get_level_semester_states()

        if current_sessions:
            summary = get_financial_summary(sessions=current_sessions)
            context['revenue_this_session'] = summary['collected']
            context['outstanding_this_session'] = summary['outstanding']
            context['defaulter_count'] = get_defaulters(sessions=current_sessions).count()

        context['total_departments'] = Department.objects.count()
        context['total_courses'] = Course.objects.count()
        context['total_offerings'] = CourseOffering.objects.count()
        context['published_results_count'] = Grade.objects.filter(status=Grade.Status.PUBLISHED).count()

        role_labels = dict(Role.choices)
        role_counts = User.objects.values('role').annotate(count=Count('id')).order_by('role')
        context['role_breakdown'] = [
            {'label': role_labels.get(row['role'], 'Unassigned'), 'count': row['count']}
            for row in role_counts
        ]
        return context
