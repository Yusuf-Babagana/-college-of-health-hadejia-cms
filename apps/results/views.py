from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin
from apps.courses.models import CourseOffering

from . import selectors, services
from .forms import GradeBandForm, GradeEntryFormSet
from .models import Grade, GradeBand


# ---------------------------------------------------------------------------
# Grade bands (Exam Officer configures the grading scale)
# ---------------------------------------------------------------------------

class GradeBandRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.EXAM_OFFICER, Role.SUPER_ADMIN)


class GradeBandListView(GradeBandRoleMixin, ListView):
    template_name = 'results/grade_band_list.html'
    context_object_name = 'grade_bands'

    def get_queryset(self):
        return selectors.get_grade_bands()


class GradeBandCreateView(GradeBandRoleMixin, CreateView):
    model = GradeBand
    form_class = GradeBandForm
    template_name = 'results/grade_band_form.html'
    success_url = reverse_lazy('results:grade_band_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Grade Band'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Grade band "{form.instance}" created.')
        return super().form_valid(form)


class GradeBandUpdateView(GradeBandRoleMixin, UpdateView):
    model = GradeBand
    form_class = GradeBandForm
    template_name = 'results/grade_band_form.html'
    success_url = reverse_lazy('results:grade_band_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Grade band "{form.instance}" updated.')
        return super().form_valid(form)


class GradeBandDeleteView(GradeBandRoleMixin, View):
    def post(self, request, pk):
        band = get_object_or_404(GradeBand, pk=pk)
        band.delete(hard=True)  # reference data - a mistaken band should just go away, no archive/restore needed
        messages.success(request, 'Grade band removed.')
        return redirect('results:grade_band_list')


# ---------------------------------------------------------------------------
# Lecturer: grade entry + submit
# ---------------------------------------------------------------------------

class LecturerResultsRoleMixin(RoleRequiredMixin):
    """Anyone with a Lecturer profile handles grading for their own
    assigned offerings - including an HOD, who keeps their Lecturer
    profile after promotion (see apps.lecturers.models.Lecturer.clean())
    and is often still assigned courses to teach directly.
    """
    allowed_roles = (Role.LECTURER, Role.HOD)


class LecturerOfferingListView(LecturerResultsRoleMixin, ListView):
    """FR-LEC-01: defaults to THE current active semester's workload;
    a semester filter lets the lecturer reach past offerings too, so a
    semester going inactive mid-grading never strands unsubmitted work.
    """
    template_name = 'results/lecturer_offering_list.html'
    context_object_name = 'offerings'

    def get_queryset(self):
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        if not lecturer_profile:
            return CourseOffering.objects.none()

        # No single global "active semester" exists anymore (levels run
        # different semesters), so the unfiltered default is all semesters.
        semester_param = self.request.GET.get('semester')
        semester = None if semester_param in (None, '', 'all') else semester_param
        self.current_semester_filter = semester_param or 'all'

        return selectors.get_offerings_for_lecturer(lecturer_profile, semester=semester)

    def get_context_data(self, **kwargs):
        from apps.academics.models import Semester

        context = super().get_context_data(**kwargs)
        context['semesters'] = Semester.objects.select_related('session')
        context['current_semester_filter'] = self.current_semester_filter
        return context


class ClassListView(LecturerResultsRoleMixin, TemplateView):
    template_name = 'results/class_list.html'

    def get_context_data(self, **kwargs):
        from apps.courses.selectors import get_class_list_for_offering

        context = super().get_context_data(**kwargs)
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        offering = get_object_or_404(CourseOffering, pk=kwargs['pk'], lecturer=lecturer_profile)
        context['offering'] = offering
        context['registrations'] = get_class_list_for_offering(offering)
        return context


class ClassListExportView(LecturerResultsRoleMixin, View):
    """FR-LEC-02: export the class roster as CSV."""

    def get(self, request, pk):
        import csv

        from django.http import HttpResponse

        from apps.courses.selectors import get_class_list_for_offering

        lecturer_profile = getattr(request.user, 'lecturer_profile', None)
        offering = get_object_or_404(CourseOffering, pk=pk, lecturer=lecturer_profile)
        registrations = get_class_list_for_offering(offering)

        filename = f'class-list-{offering.course.code}-{offering.semester}.csv'.replace('/', '-').replace(' ', '-')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['Matric Number', 'Name', 'Level', 'Email', 'Phone'])
        for reg in registrations:
            writer.writerow([
                reg.student.matric_number,
                reg.student.user.get_full_name(),
                reg.student.get_level_display(),
                reg.student.user.email,
                reg.student.user.phone_number,
            ])
        return response


class GradeEntryView(LecturerResultsRoleMixin, View):
    template_name = 'results/grade_entry.html'

    def get_offering(self, request, pk):
        lecturer_profile = getattr(request.user, 'lecturer_profile', None)
        return get_object_or_404(CourseOffering, pk=pk, lecturer=lecturer_profile)

    def get_formset(self, offering, data=None):
        editable_qs = selectors.get_grades_for_offering(offering).filter(
            status__in=[Grade.Status.DRAFT, Grade.Status.REJECTED],
        ).order_by('student__matric_number')
        return GradeEntryFormSet(data, queryset=editable_qs, prefix='grades')

    def _locked_grades(self, offering):
        return selectors.get_grades_for_offering(offering).exclude(
            status__in=[Grade.Status.DRAFT, Grade.Status.REJECTED],
        ).order_by('student__matric_number')

    def get(self, request, pk):
        offering = self.get_offering(request, pk)
        services.sync_grades_for_offering(offering)
        formset = self.get_formset(offering)
        return render(request, self.template_name, {
            'offering': offering, 'formset': formset, 'locked_grades': self._locked_grades(offering),
        })

    def post(self, request, pk):
        offering = self.get_offering(request, pk)
        formset = self.get_formset(offering, data=request.POST)
        if formset.is_valid():
            formset.save()
            messages.success(request, 'Grades saved.')
            return redirect('results:grade_entry', pk=offering.pk)

        messages.error(request, 'Please correct the errors below.')
        return render(request, self.template_name, {
            'offering': offering, 'formset': formset, 'locked_grades': self._locked_grades(offering),
        })


class SubmitGradesView(LecturerResultsRoleMixin, View):
    def post(self, request, pk):
        lecturer_profile = getattr(request.user, 'lecturer_profile', None)
        offering = get_object_or_404(CourseOffering, pk=pk, lecturer=lecturer_profile)
        count = services.submit_grades(offering)
        if count:
            messages.success(request, f'Submitted {count} grade(s) for HOD review.')
        else:
            messages.warning(request, 'No editable grades to submit.')
        return redirect('results:grade_entry', pk=offering.pk)


# ---------------------------------------------------------------------------
# HOD: review submitted grades
# ---------------------------------------------------------------------------

class HODReviewRoleMixin(RoleRequiredMixin):
    """Super Admin gets cross-department oversight of the review queue,
    since their account isn't tied to a single Lecturer profile.
    """
    allowed_roles = (Role.HOD, Role.SUPER_ADMIN)

    def get_department(self):
        lecturer_profile = getattr(self.request.user, 'lecturer_profile', None)
        return lecturer_profile.department if lecturer_profile else None

    def is_overseer(self):
        return self.request.user.role == Role.SUPER_ADMIN

    def get_grade_or_404(self, pk):
        department = self.get_department()
        if department:
            return get_object_or_404(Grade, pk=pk, course_offering__course__department=department)
        if self.is_overseer():
            return get_object_or_404(Grade, pk=pk)
        raise Http404


class GradeReviewListView(HODReviewRoleMixin, PaginatedListMixin, ListView):
    template_name = 'results/grade_review_list.html'
    context_object_name = 'grades'

    def get_queryset(self):
        department = self.get_department()
        if not department and not self.is_overseer():
            return Grade.objects.none()

        filter_department = department or self.request.GET.get('department')
        return selectors.get_submitted_grades_for_department(filter_department)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department = self.get_department()
        context['department'] = department
        context['is_overseer'] = self.is_overseer()
        if self.is_overseer():
            from apps.departments.selectors import get_active_departments

            context['departments'] = get_active_departments()
            context['current_department'] = self.request.GET.get('department', '')
        return context


class ApproveGradeView(HODReviewRoleMixin, View):
    def post(self, request, pk):
        grade = self.get_grade_or_404(pk)
        try:
            services.review_grade(grade, approve=True, reviewer=request.user)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Approved {grade}.')
        return redirect('results:grade_review_list')


class RejectGradeView(HODReviewRoleMixin, View):
    def post(self, request, pk):
        grade = self.get_grade_or_404(pk)
        comment = request.POST.get('comment', '').strip()
        try:
            services.review_grade(grade, approve=False, reviewer=request.user, comment=comment)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Rejected {grade}. The lecturer can now correct and resubmit it.')
        return redirect('results:grade_review_list')


# ---------------------------------------------------------------------------
# Exam Officer: compile + publish
# ---------------------------------------------------------------------------

class ExamOfficerRoleMixin(RoleRequiredMixin):
    allowed_roles = (Role.EXAM_OFFICER, Role.SUPER_ADMIN)


class GradeCollationListView(ExamOfficerRoleMixin, PaginatedListMixin, ListView):
    """FR-EXM-01: cross-department visibility into every locked grade
    (submitted, approved, rejected, or published) across all semesters
    by default - not just the ones ready to publish.
    """
    template_name = 'results/grade_collation_list.html'
    context_object_name = 'grades'

    def get_queryset(self):
        # No single global "active semester" exists anymore (levels run
        # different semesters), so the unfiltered default is all semesters.
        semester_param = self.request.GET.get('semester')
        semester = None if semester_param in (None, '', 'all') else semester_param
        self.current_semester_filter = semester_param or 'all'

        return selectors.get_collated_grades(
            department=self.request.GET.get('department'),
            semester=semester,
            status=self.request.GET.get('status'),
        )

    def get_context_data(self, **kwargs):
        from apps.academics.models import Semester
        from apps.departments.selectors import get_active_departments

        context = super().get_context_data(**kwargs)
        context['departments'] = get_active_departments()
        context['semesters'] = Semester.objects.select_related('session')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_semester'] = self.current_semester_filter
        context['current_status'] = self.request.GET.get('status', '')
        context['status_choices'] = Grade.Status.choices
        return context


class UnlockGradeView(ExamOfficerRoleMixin, View):
    """FR-EXM-04: reopen any locked grade for lecturer correction."""
    def post(self, request, pk):
        grade = get_object_or_404(Grade, pk=pk)
        comment = request.POST.get('comment', '').strip()
        try:
            services.unlock_grade(grade, comment=comment)
        except ValidationError as exc:
            messages.error(request, exc.message)
        else:
            messages.success(request, f'Unlocked {grade} - the lecturer can now correct and resubmit it.')
        return redirect('results:grade_collation_list')


class ApprovedGradeListView(ExamOfficerRoleMixin, PaginatedListMixin, ListView):
    """FR: Compile Results - HOD-approved grades awaiting publication."""
    template_name = 'results/approved_grade_list.html'
    context_object_name = 'grades'

    def get_queryset(self):
        return selectors.get_approved_grades(
            department=self.request.GET.get('department'),
            semester=self.request.GET.get('semester'),
        )

    def get_context_data(self, **kwargs):
        from apps.academics.models import Semester
        from apps.departments.selectors import get_active_departments

        context = super().get_context_data(**kwargs)
        context['departments'] = get_active_departments()
        context['semesters'] = Semester.objects.select_related('session')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_semester'] = self.request.GET.get('semester', '')

        offering_ids = set(self.get_queryset().values_list('course_offering_id', flat=True))
        context['offerings'] = CourseOffering.objects.filter(pk__in=offering_ids).select_related('course', 'semester')
        return context


class PublishGradesView(ExamOfficerRoleMixin, View):
    """FR: only the Exam Officer publishes results - per course offering."""
    def post(self, request, pk):
        offering = get_object_or_404(CourseOffering, pk=pk)
        count = services.publish_grades(offering)
        if count:
            messages.success(request, f'Published {count} result(s) for {offering}.')
        else:
            messages.warning(request, 'No approved grades to publish for this offering.')
        return redirect('results:approved_grade_list')


# ---------------------------------------------------------------------------
# Student: view results
# ---------------------------------------------------------------------------

class MyResultsView(RoleRequiredMixin, TemplateView):
    allowed_roles = (Role.STUDENT,)
    template_name = 'results/my_results.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student_profile = getattr(self.request.user, 'student_profile', None)
        context['student_profile'] = student_profile
        if not student_profile:
            return context

        context.update(selectors.get_transcript_for_student(student_profile))
        return context


class MyScoreSheetView(RoleRequiredMixin, TemplateView):
    """FR: a student's live CA1/CA2 scores for every course they're
    registered for, visible the moment a lecturer saves them - unlike
    "My Results", this doesn't wait for submission/approval/publish.
    """
    allowed_roles = (Role.STUDENT,)
    template_name = 'results/my_score_sheet.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student_profile = getattr(self.request.user, 'student_profile', None)
        context['student_profile'] = student_profile
        if student_profile:
            context['score_rows'] = selectors.get_score_sheet_for_student(student_profile)
        return context


# ---------------------------------------------------------------------------
# Transcript (student self-service + Exam Officer lookup)
# ---------------------------------------------------------------------------

class MyTranscriptPDFView(RoleRequiredMixin, View):
    allowed_roles = (Role.STUDENT,)

    def get(self, request):
        from apps.core.utils.pdf import render_to_pdf_response

        student_profile = getattr(request.user, 'student_profile', None)
        if not student_profile:
            messages.error(request, 'No student profile linked to your account.')
            return redirect('results:my_results')

        transcript = selectors.get_transcript_for_student(student_profile)
        return render_to_pdf_response(
            'results/transcript_pdf.html',
            {
                'student': student_profile,
                'college_name': 'College of Health Sciences and Technology, Hadejia',
                **transcript,
            },
            filename=f'transcript-{student_profile.matric_number}.pdf'.replace('/', '-'),
        )


class TranscriptSearchView(ExamOfficerRoleMixin, TemplateView):
    template_name = 'results/transcript_search.html'

    def get_context_data(self, **kwargs):
        from apps.students.selectors import get_student_list

        context = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '').strip()
        context['search_query'] = query
        context['students'] = get_student_list(search=query) if query else None
        return context


class StudentTranscriptPDFView(ExamOfficerRoleMixin, View):
    def get(self, request, pk):
        from apps.core.utils.pdf import render_to_pdf_response
        from apps.students.models import Student

        student = get_object_or_404(Student, pk=pk)
        transcript = selectors.get_transcript_for_student(student)
        return render_to_pdf_response(
            'results/transcript_pdf.html',
            {
                'student': student,
                'college_name': 'College of Health Sciences and Technology, Hadejia',
                **transcript,
            },
            filename=f'transcript-{student.matric_number}.pdf'.replace('/', '-'),
        )


# ---------------------------------------------------------------------------
# Broadsheet (Exam Officer, per course offering)
# ---------------------------------------------------------------------------

class BroadsheetPDFView(ExamOfficerRoleMixin, View):
    def get(self, request, pk):
        from apps.core.utils.pdf import render_to_pdf_response

        offering = get_object_or_404(CourseOffering, pk=pk)
        grades = list(selectors.get_broadsheet_for_offering(offering))
        pass_count = sum(1 for g in grades if g.letter_grade != 'F')

        return render_to_pdf_response(
            'results/broadsheet_pdf.html',
            {
                'offering': offering,
                'grades': grades,
                'total_count': len(grades),
                'pass_count': pass_count,
                'fail_count': len(grades) - pass_count,
                'college_name': 'College of Health Sciences and Technology, Hadejia',
            },
            filename=f'broadsheet-{offering.course.code}-{offering.semester}.pdf'.replace('/', '-').replace(' ', '-'),
        )


class BroadsheetCSVExportView(ExamOfficerRoleMixin, View):
    """FR-EXM-06: the same per-course broadsheet as CSV/Excel."""

    def get(self, request, pk):
        import csv

        from django.http import HttpResponse

        offering = get_object_or_404(CourseOffering, pk=pk)
        grades = selectors.get_broadsheet_for_offering(offering)

        filename = f'broadsheet-{offering.course.code}-{offering.semester}.csv'.replace('/', '-').replace(' ', '-')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['Matric Number', 'Name', 'CA', 'Exam', 'Total', 'Grade', 'Points'])
        for grade in grades:
            writer.writerow([
                grade.student.matric_number,
                grade.student.user.get_full_name(),
                grade.ca_score,
                grade.exam_score,
                grade.total_score,
                grade.letter_grade or '',
                grade.grade_point if grade.grade_point is not None else '',
            ])
        return response


class MasterBroadsheetView(ExamOfficerRoleMixin, TemplateView):
    """FR-EXM-06: the pivoted master broadsheet for one department+level
    +semester, ready for the Academic Board - viewable here, exportable
    as CSV below.
    """
    template_name = 'results/master_broadsheet.html'

    def get_context_data(self, **kwargs):
        from apps.academics.models import Semester
        from apps.core.constants import Level
        from apps.departments.selectors import get_active_departments

        context = super().get_context_data(**kwargs)
        context['departments'] = get_active_departments()
        context['semesters'] = Semester.objects.select_related('session')
        context['level_choices'] = Level.choices
        context['current_department'] = self.request.GET.get('department', '')
        context['current_semester'] = self.request.GET.get('semester', '')
        context['current_level'] = self.request.GET.get('level', '')

        department_id = self.request.GET.get('department')
        semester_id = self.request.GET.get('semester')
        level = self.request.GET.get('level')
        if department_id and semester_id and level:
            from apps.departments.models import Department

            department = get_object_or_404(Department, pk=department_id)
            semester = get_object_or_404(Semester, pk=semester_id)
            context['broadsheet'] = selectors.get_master_broadsheet(
                department=department, semester=semester, level=level,
            )
            context['selected_department'] = department
            context['selected_semester'] = semester
            context['selected_level'] = int(level)

        return context


class MasterBroadsheetExportView(ExamOfficerRoleMixin, View):
    """FR-EXM-06: the same pivot, as a downloadable CSV for the board."""

    def get(self, request):
        import csv

        from django.http import HttpResponse

        from apps.academics.models import Semester
        from apps.departments.models import Department

        department = get_object_or_404(Department, pk=request.GET.get('department'))
        semester = get_object_or_404(Semester, pk=request.GET.get('semester'))
        level = request.GET.get('level')

        broadsheet = selectors.get_master_broadsheet(department=department, semester=semester, level=level)

        filename = f'broadsheet-{department.code}-{level}L-{semester}.csv'.replace('/', '-').replace(' ', '-')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(
            ['Matric Number', 'Name'] + [course.code for course in broadsheet['courses']] + ['GPA'],
        )
        for row in broadsheet['rows']:
            writer.writerow(
                [row['student'].matric_number, row['student'].user.get_full_name()]
                + [(grade.letter_grade if grade else '') for grade in row['grades']]
                + [row['gpa'] if row['gpa'] is not None else ''],
            )
        return response
