"""
Automated tests for the Master Broadsheet - the central acceptance
criterion for this work is Test 2 (shared course isolation): a course
shared by two programmes must appear as a column on both broadsheets,
while a student who took it must appear as a row on ONLY their own
programme's broadsheet.

Uses TestCase throughout: every test runs inside a transaction Django
rolls back afterwards, against Django's own separate test database -
never the real development database, and nothing here persists past the
test run.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicSession, LevelSemesterState, Semester
from apps.admissions.models import Programme
from apps.core.constants import Level, SemesterName
from apps.courses import services as course_services
from apps.courses.models import Course, CourseOffering, CourseRegistration
from apps.courses.selectors import get_current_offering_for_course
from apps.departments.models import Department
from apps.results.models import Grade, GradeBand
from apps.results.selectors import get_carryover_courses, get_master_broadsheet
from apps.students.models import Student
from apps.students.services import create_student


class MasterBroadsheetTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2099/2100')
        cls.semester = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)

        cls.dept = Department.objects.create(name='Test Community Health', code='TCH')
        cls.gst_dept = Department.objects.create(
            name='Test General Studies', code='TGS', is_general_studies=True,
        )

        cls.programme_a = Programme.objects.create(
            name='Test Diploma', short_code='TDIP', department=cls.dept, duration_levels=4,
        )
        cls.programme_b = Programme.objects.create(
            name='Test Certificate', short_code='TCERT', department=cls.dept, duration_levels=2,
        )

    def _student(self, *, programme=None, level=Level.LEVEL_100, suffix):
        student, _ = create_student(
            first_name='Test', last_name=f'Student{suffix}', email=f'test.student{suffix}@example.test',
            matric_number=f'TST/2099/{suffix}', department=self.dept, level=level,
            admission_session=self.session, programme=programme,
        )
        return student

    def _course(self, *, code, level=Level.LEVEL_100, department=None, programme=None):
        return Course.objects.create(
            code=code, title=f'Course {code}', credit_units=2, level=level,
            department=department or self.dept, programme=programme, semester_name=SemesterName.FIRST,
        )

    def _offering(self, course):
        return CourseOffering.objects.create(course=course, semester=self.semester, capacity=50)

    def _register(self, student, offering):
        return CourseRegistration.objects.create(
            student=student, course_offering=offering, status=CourseRegistration.Status.REGISTERED,
        )

    # --- Test 1: programme-specific course ---
    def test_programme_specific_course_shows_its_own_student(self):
        course = self._course(code='TST201', programme=self.programme_a)
        offering = self._offering(course)
        student = self._student(programme=self.programme_a, suffix='1')
        self._register(student, offering)

        sheet = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)

        self.assertIn(course, sheet['courses'])
        self.assertEqual([r['student'] for r in sheet['rows']], [student])

    # --- Test 2: THE mandatory shared-course isolation invariant ---
    def test_shared_course_isolates_students_by_own_programme(self):
        shared_course = self._course(code='TST202', programme=self.programme_a)
        shared_course.eligible_programmes.set([self.programme_a, self.programme_b])
        offering = self._offering(shared_course)

        student_a = self._student(programme=self.programme_a, suffix='A')
        student_b = self._student(programme=self.programme_b, level=Level.LEVEL_100, suffix='B')
        self._register(student_a, offering)
        self._register(student_b, offering)

        sheet_a = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)
        sheet_b = get_master_broadsheet(programme=self.programme_b, semester=self.semester, level=Level.LEVEL_100)

        # Column: the shared course appears on BOTH broadsheets.
        self.assertIn(shared_course, sheet_a['courses'])
        self.assertIn(shared_course, sheet_b['courses'])

        # Rows: each student appears ONLY on their own programme's sheet.
        students_on_a = {r['student'] for r in sheet_a['rows']}
        students_on_b = {r['student'] for r in sheet_b['rows']}
        self.assertIn(student_a, students_on_a)
        self.assertNotIn(student_b, students_on_a)
        self.assertIn(student_b, students_on_b)
        self.assertNotIn(student_a, students_on_b)

    # --- Test 3: General Studies blanket inclusion ---
    def test_untagged_general_studies_course_appears_on_every_programme(self):
        gst_course = self._course(code='TST203', department=self.gst_dept)
        offering = self._offering(gst_course)

        student_a = self._student(programme=self.programme_a, suffix='C')
        student_b = self._student(programme=self.programme_b, suffix='D')
        self._register(student_a, offering)
        self._register(student_b, offering)

        sheet_a = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)
        sheet_b = get_master_broadsheet(programme=self.programme_b, semester=self.semester, level=Level.LEVEL_100)

        self.assertIn(gst_course, sheet_a['courses'])
        self.assertIn(gst_course, sheet_b['courses'])
        self.assertIn(student_a, {r['student'] for r in sheet_a['rows']})
        self.assertIn(student_b, {r['student'] for r in sheet_b['rows']})

    # --- Test 4: explicit narrowing overrides the General Studies fallback ---
    def test_general_studies_course_narrowed_to_one_programme_does_not_leak(self):
        gst_course = self._course(code='TST204', department=self.gst_dept)
        gst_course.eligible_programmes.set([self.programme_a])
        offering = self._offering(gst_course)

        student_b = self._student(programme=self.programme_b, suffix='E')
        self._register(student_b, offering)

        sheet_a = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)
        sheet_b = get_master_broadsheet(programme=self.programme_b, semester=self.semester, level=Level.LEVEL_100)

        self.assertIn(gst_course, sheet_a['courses'])
        self.assertNotIn(gst_course, sheet_b['courses'])
        # Student B registered, but the course isn't even a column on B's
        # sheet once narrowed away from them - so they can't be a row either.
        self.assertNotIn(student_b, {r['student'] for r in sheet_b['rows']})

    # --- Test 5: student with no Programme is never inferred onto a sheet ---
    def test_student_with_no_programme_does_not_appear_anywhere(self):
        course = self._course(code='TST205', programme=self.programme_a)
        offering = self._offering(course)
        student = self._student(programme=None, suffix='F')
        self._register(student, offering)

        sheet_a = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)
        sheet_b = get_master_broadsheet(programme=self.programme_b, semester=self.semester, level=Level.LEVEL_100)

        self.assertNotIn(student, {r['student'] for r in sheet_a['rows']})
        self.assertNotIn(student, {r['student'] for r in sheet_b['rows']})

    # --- Test 6: multiple shared courses, still only the student's own sheet ---
    def test_multiple_shared_courses_still_isolate_by_programme(self):
        course_1 = self._course(code='TST206', programme=self.programme_a)
        course_1.eligible_programmes.set([self.programme_a, self.programme_b])
        course_2 = self._course(code='TST207', programme=self.programme_a)
        course_2.eligible_programmes.set([self.programme_a, self.programme_b])
        offering_1, offering_2 = self._offering(course_1), self._offering(course_2)

        student_a = self._student(programme=self.programme_a, suffix='G')
        student_b = self._student(programme=self.programme_b, suffix='H')
        for student in (student_a, student_b):
            self._register(student, offering_1)
            self._register(student, offering_2)

        sheet_a = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)
        sheet_b = get_master_broadsheet(programme=self.programme_b, semester=self.semester, level=Level.LEVEL_100)

        self.assertEqual({r['student'] for r in sheet_a['rows']}, {student_a})
        self.assertEqual({r['student'] for r in sheet_b['rows']}, {student_b})

    # --- Test 11: level isolation ---
    def test_level_isolation(self):
        course_100 = self._course(code='TST208', level=Level.LEVEL_100, programme=self.programme_a)
        offering_100 = self._offering(course_100)

        student_100 = self._student(programme=self.programme_a, level=Level.LEVEL_100, suffix='I')
        student_200 = self._student(programme=self.programme_a, level=Level.LEVEL_200, suffix='J')
        self._register(student_100, offering_100)
        # A Level 200 student carrying over/repeating a Level 100 course -
        # still registered for the same offering.
        self._register(student_200, offering_100)

        sheet_level_100 = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)

        rows = {r['student'] for r in sheet_level_100['rows']}
        self.assertIn(student_100, rows)
        self.assertNotIn(student_200, rows, 'A Level 200 student must not appear on the Level 100 broadsheet.')

    # --- Test 12: shared course + different level ---
    def test_shared_course_does_not_leak_across_levels(self):
        shared_course = self._course(code='TST209', level=Level.LEVEL_100, programme=self.programme_a)
        shared_course.eligible_programmes.set([self.programme_a, self.programme_b])
        offering = self._offering(shared_course)

        # Same programme (A), same shared course, but two different levels.
        student_100 = self._student(programme=self.programme_a, level=Level.LEVEL_100, suffix='K')
        student_200 = self._student(programme=self.programme_a, level=Level.LEVEL_200, suffix='L')
        self._register(student_100, offering)
        self._register(student_200, offering)

        sheet = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)

        rows = {r['student'] for r in sheet['rows']}
        self.assertIn(student_100, rows)
        self.assertNotIn(student_200, rows)

    # --- Withdrawn/suspended students excluded (approved default policy) ---
    def test_withdrawn_and_suspended_students_are_excluded(self):
        course = self._course(code='TST210', programme=self.programme_a)
        offering = self._offering(course)

        active_student = self._student(programme=self.programme_a, suffix='M')
        withdrawn_student = self._student(programme=self.programme_a, suffix='N')
        withdrawn_student.status = Student.Status.WITHDRAWN
        withdrawn_student.save(update_fields=['status'])
        suspended_student = self._student(programme=self.programme_a, suffix='O')
        suspended_student.status = Student.Status.SUSPENDED
        suspended_student.save(update_fields=['status'])

        for student in (active_student, withdrawn_student, suspended_student):
            self._register(student, offering)

        sheet = get_master_broadsheet(programme=self.programme_a, semester=self.semester, level=Level.LEVEL_100)

        rows = {r['student'] for r in sheet['rows']}
        self.assertIn(active_student, rows)
        self.assertNotIn(withdrawn_student, rows)
        self.assertNotIn(suspended_student, rows)


class CarryoverTests(TestCase):
    """FR-STU-CARRY: "My Carryover" - a course counts as an outstanding
    carryover when the student's most recent PUBLISHED attempt at it was
    a Fail, and it registers itself the moment a fresh CourseOffering of
    that exact course opens for registration.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Carryover Department', code='CRY')
        # Mirrors the college's 4-point scale: A=4/B=3/C=2/D=1/E=0.5/F=0.
        GradeBand.objects.create(min_score=70, max_score=100, letter='A', grade_point='4.00')
        GradeBand.objects.create(min_score=60, max_score=69, letter='B', grade_point='3.00')
        GradeBand.objects.create(min_score=50, max_score=59, letter='C', grade_point='2.00')
        GradeBand.objects.create(min_score=45, max_score=49, letter='D', grade_point='1.00')
        GradeBand.objects.create(min_score=40, max_score=44, letter='E', grade_point='0.50')
        GradeBand.objects.create(min_score=0, max_score=39, letter='F', grade_point='0.00')

    def _session(self, name):
        return AcademicSession.objects.create(name=name)

    def _semester(self, session, name=SemesterName.FIRST, *, open_now=False):
        now = timezone.now()
        return Semester.objects.create(
            session=session, name=name,
            registration_start=now - timedelta(days=1) if open_now else None,
            registration_end=now + timedelta(days=30) if open_now else None,
        )

    def _course(self, code, level=Level.LEVEL_100):
        return Course.objects.create(
            code=code, title=code, credit_units=3, level=level,
            department=self.dept, semester_name=SemesterName.FIRST,
        )

    def _student(self, *, level, admission_session, suffix):
        student, _ = create_student(
            first_name='Test', last_name=f'Carryover{suffix}', email=f'carryover{suffix}@example.test',
            matric_number=f'CRY/2099/{suffix}', department=self.dept, level=level,
            admission_session=admission_session,
        )
        return student

    def _grade(self, student, offering, *, total, status=Grade.Status.PUBLISHED):
        exam = min(total, 60)
        remaining = total - exam
        ca1 = min(remaining, 20)
        remaining -= ca1
        ca2 = min(remaining, 20)
        return Grade.objects.create(
            student=student, course_offering=offering,
            ca1_score=ca1, ca2_score=ca2, exam_score=exam, status=status,
        )

    def test_failed_course_appears_as_carryover(self):
        old_session = self._session('2098/2099')
        old_semester = self._semester(old_session)
        course = self._course('CRY101')
        old_offering = CourseOffering.objects.create(course=course, semester=old_semester, capacity=50)
        student = self._student(level=Level.LEVEL_200, admission_session=old_session, suffix='1')
        grade = self._grade(student, old_offering, total=20)

        rows = get_carryover_courses(student)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['course'], course)
        self.assertEqual(rows[0]['failed_grade'], grade)
        self.assertEqual(rows[0]['failed_offering'], old_offering)

    def test_passed_course_does_not_appear_as_carryover(self):
        session = self._session('2098/2099')
        semester = self._semester(session)
        course = self._course('CRY102')
        offering = CourseOffering.objects.create(course=course, semester=semester, capacity=50)
        student = self._student(level=Level.LEVEL_100, admission_session=session, suffix='2')
        self._grade(student, offering, total=75)

        self.assertEqual(get_carryover_courses(student), [])

    def test_retaken_and_passed_course_clears_the_carryover(self):
        old_session = self._session('2097/2098')
        old_semester = self._semester(old_session)
        new_session = self._session('2098/2099')
        new_semester = self._semester(new_session)
        course = self._course('CRY103')
        old_offering = CourseOffering.objects.create(course=course, semester=old_semester, capacity=50)
        new_offering = CourseOffering.objects.create(course=course, semester=new_semester, capacity=50)
        student = self._student(level=Level.LEVEL_200, admission_session=old_session, suffix='3')
        self._grade(student, old_offering, total=20)
        self._grade(student, new_offering, total=65)

        self.assertEqual(get_carryover_courses(student), [])

    def test_ungraded_draft_attempt_is_ignored(self):
        session = self._session('2098/2099')
        semester = self._semester(session)
        course = self._course('CRY104')
        offering = CourseOffering.objects.create(course=course, semester=semester, capacity=50)
        student = self._student(level=Level.LEVEL_100, admission_session=session, suffix='4')
        self._grade(student, offering, total=10, status=Grade.Status.DRAFT)

        self.assertEqual(get_carryover_courses(student), [])

    def test_sync_auto_registers_when_a_fresh_offering_opens(self):
        old_session = self._session('2098/2099')
        old_semester = self._semester(old_session)
        new_session = self._session('2099/2100')
        new_semester = self._semester(new_session, open_now=True)
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=new_semester)

        course = self._course('CRY105', level=Level.LEVEL_100)
        old_offering = CourseOffering.objects.create(course=course, semester=old_semester, capacity=50)
        new_offering = CourseOffering.objects.create(course=course, semester=new_semester, capacity=50)

        # Now Level 200 - the fresh offering is for a Level 100 course,
        # which normal self-service registration would never permit.
        student = self._student(level=Level.LEVEL_200, admission_session=old_session, suffix='5')
        self._grade(student, old_offering, total=20)

        created = course_services.sync_carryover_registrations(student)

        self.assertEqual(len(created), 1)
        self.assertTrue(
            CourseRegistration.objects.filter(
                student=student, course_offering=new_offering, status=CourseRegistration.Status.REGISTERED,
            ).exists()
        )

    def test_sync_does_not_duplicate_on_a_second_call(self):
        old_session = self._session('2098/2099')
        old_semester = self._semester(old_session)
        new_session = self._session('2099/2100')
        new_semester = self._semester(new_session, open_now=True)
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=new_semester)

        course = self._course('CRY106', level=Level.LEVEL_100)
        old_offering = CourseOffering.objects.create(course=course, semester=old_semester, capacity=50)
        CourseOffering.objects.create(course=course, semester=new_semester, capacity=50)

        student = self._student(level=Level.LEVEL_200, admission_session=old_session, suffix='6')
        self._grade(student, old_offering, total=20)

        course_services.sync_carryover_registrations(student)
        second_call = course_services.sync_carryover_registrations(student)

        self.assertEqual(second_call, [])
        self.assertEqual(
            CourseRegistration.objects.filter(student=student, course_offering__course=course).count(), 1,
        )

    def test_sync_is_a_noop_without_a_fresh_offering(self):
        old_session = self._session('2098/2099')
        old_semester = self._semester(old_session)
        course = self._course('CRY107', level=Level.LEVEL_100)
        old_offering = CourseOffering.objects.create(course=course, semester=old_semester, capacity=50)
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=old_semester)

        student = self._student(level=Level.LEVEL_200, admission_session=old_session, suffix='7')
        self._grade(student, old_offering, total=20)

        created = course_services.sync_carryover_registrations(student)

        self.assertEqual(created, [])
        self.assertEqual(get_current_offering_for_course(course).pk, old_offering.pk)

    def test_register_carryover_course_bypasses_level_eligibility(self):
        old_session = self._session('2098/2099')
        old_semester = self._semester(old_session)
        new_session = self._session('2099/2100')
        new_semester = self._semester(new_session, open_now=True)

        course = self._course('CRY108', level=Level.LEVEL_100)
        old_offering = CourseOffering.objects.create(course=course, semester=old_semester, capacity=50)
        new_offering = CourseOffering.objects.create(course=course, semester=new_semester, capacity=50)

        student = self._student(level=Level.LEVEL_200, admission_session=old_session, suffix='8')
        self._grade(student, old_offering, total=20)

        # A normal self-service register_course call must still be
        # rejected - level eligibility is only bypassed for the
        # carryover route.
        with self.assertRaises(ValidationError):
            course_services.register_course(student=student, course_offering=new_offering)

        registration = course_services.register_carryover_course(student=student, course_offering=new_offering)

        self.assertEqual(registration.status, CourseRegistration.Status.REGISTERED)

    def test_my_carryover_page_shows_the_course_and_registers_it(self):
        from django.test import Client
        from django.urls import reverse

        old_session = self._session('2098/2099')
        old_semester = self._semester(old_session)
        new_session = self._session('2099/2100')
        new_semester = self._semester(new_session, open_now=True)
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=new_semester)

        course = self._course('CRY109', level=Level.LEVEL_100)
        old_offering = CourseOffering.objects.create(course=course, semester=old_semester, capacity=50)
        CourseOffering.objects.create(course=course, semester=new_semester, capacity=50)

        student = self._student(level=Level.LEVEL_200, admission_session=old_session, suffix='9')
        student.user.must_change_password = False
        student.user.save(update_fields=['must_change_password'])
        self._grade(student, old_offering, total=20)

        client = Client()
        client.force_login(student.user)

        response = client.get(reverse('courses:my_carryover'))

        self.assertContains(response, 'CRY109')
        self.assertContains(response, 'Registered for retake')
        self.assertTrue(
            CourseRegistration.objects.filter(
                student=student, course_offering__course=course, status=CourseRegistration.Status.REGISTERED,
            ).exists()
        )


class GradeBandScopingTests(TestCase):
    """FR-EXM-05: Grade Bands can be scoped to a Department and/or
    Programme - most-specific-wins resolution (programme > department >
    college-wide default), and only bands in the exact same scope are
    checked for overlapping score ranges against each other.
    """

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2096/2097')
        cls.semester = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)

        cls.dept_a = Department.objects.create(name='Scoping Dept A', code='SDA')
        cls.dept_b = Department.objects.create(name='Scoping Dept B', code='SDB')
        cls.programme_a1 = Programme.objects.create(
            name='Scoping Programme A1', short_code='SPA1', department=cls.dept_a, duration_levels=4,
        )

        cls.course = Course.objects.create(
            code='SCOPE101', title='Scoping Course', credit_units=3, level=Level.LEVEL_100,
            department=cls.dept_a, semester_name=SemesterName.FIRST,
        )
        cls.offering = CourseOffering.objects.create(course=cls.course, semester=cls.semester, capacity=50)

    def _band(self, *, department=None, programme=None, min_score=0, max_score=100, letter, grade_point):
        band = GradeBand(
            department=department, programme=programme,
            min_score=min_score, max_score=max_score, letter=letter, grade_point=grade_point,
        )
        band.full_clean()
        band.save()
        return band

    def _student(self, *, department, programme=None, suffix):
        student, _ = create_student(
            first_name='Test', last_name=f'Scope{suffix}', email=f'scope{suffix}@example.test',
            matric_number=f'SCOPE/2099/{suffix}', department=department, level=Level.LEVEL_100,
            admission_session=self.session, programme=programme,
        )
        return student

    def _grade(self, student, *, total):
        return Grade.objects.create(
            student=student, course_offering=self.offering,
            ca1_score=0, ca2_score=0, exam_score=total, status=Grade.Status.PUBLISHED,
        )

    def test_resolution_is_most_specific_scope_wins(self):
        self._band(department=None, programme=None, letter='Z', grade_point='9.00')
        self._band(department=self.dept_a, programme=None, letter='Y', grade_point='8.00')
        self._band(department=self.dept_a, programme=self.programme_a1, letter='X', grade_point='7.00')

        student_other_dept = self._student(department=self.dept_b, suffix='1')
        student_dept_a_no_programme = self._student(department=self.dept_a, suffix='2')
        student_programme_a1 = self._student(department=self.dept_a, programme=self.programme_a1, suffix='3')

        self.assertEqual(self._grade(student_other_dept, total=55).letter_grade, 'Z')
        self.assertEqual(self._grade(student_dept_a_no_programme, total=55).letter_grade, 'Y')
        self.assertEqual(self._grade(student_programme_a1, total=55).letter_grade, 'X')

    def test_overlapping_ranges_in_different_scopes_are_allowed(self):
        # Already exercised by setUp-style creation above, but assert it
        # explicitly: a department band fully overlapping the
        # college-wide default's range must not raise.
        self._band(department=None, programme=None, letter='Z', grade_point='9.00')
        try:
            self._band(department=self.dept_a, programme=None, letter='Y', grade_point='8.00')
        except ValidationError:
            self.fail('A department-scoped band must not conflict with the college-wide default.')

    def test_overlapping_ranges_in_the_same_scope_are_rejected(self):
        self._band(department=self.dept_a, programme=None, min_score=0, max_score=50, letter='C', grade_point='2.00')

        band = GradeBand(
            department=self.dept_a, programme=None,
            min_score=40, max_score=60, letter='B', grade_point='3.00',
        )
        with self.assertRaises(ValidationError):
            band.full_clean()

    def test_programme_without_department_is_rejected(self):
        band = GradeBand(
            department=None, programme=self.programme_a1,
            min_score=0, max_score=100, letter='A', grade_point='4.00',
        )
        with self.assertRaises(ValidationError) as ctx:
            band.full_clean()
        self.assertIn('department', ctx.exception.message_dict)

    def test_exam_officer_can_create_a_scoped_band_through_the_form(self):
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.models import User
        from apps.core.constants import Role

        exam_officer = User.objects.create_user(username='exam.officer', password='exampass123', role=Role.EXAM_OFFICER)
        client = Client()
        self.assertTrue(client.login(username='exam.officer', password='exampass123'))

        response = client.post(reverse('results:grade_band_create'), {
            'department': str(self.dept_a.pk),
            'programme': str(self.programme_a1.pk),
            'letter': 'A',
            'min_score': 70,
            'max_score': 100,
            'grade_point': '4.00',
        }, follow=True)

        self.assertContains(response, 'created')
        band = GradeBand.objects.get(letter='A', department=self.dept_a, programme=self.programme_a1)
        self.assertEqual(band.min_score, 70)


class MasterBroadsheetRemarkTests(TestCase):
    """FR-EXM-06: the Remark column (Distinction >= 3.50, Upper Credit
    3.00-3.49, Lower Credit 2.00-2.99, Fail below 2.00 OR any Fail this
    semester regardless of GPA, Pending with no grades yet) and Fail
    rows sinking to the bottom of the sheet.
    """

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2095/2096')
        cls.semester = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)
        cls.dept = Department.objects.create(name='Remark Department', code='RMK')
        cls.programme = Programme.objects.create(
            name='Remark Programme', short_code='RMKP', department=cls.dept, duration_levels=4,
        )

        GradeBand.objects.create(min_score=70, max_score=100, letter='A', grade_point='4.00')
        GradeBand.objects.create(min_score=60, max_score=69, letter='B', grade_point='3.00')
        GradeBand.objects.create(min_score=50, max_score=59, letter='C', grade_point='2.00')
        GradeBand.objects.create(min_score=45, max_score=49, letter='D', grade_point='1.00')
        GradeBand.objects.create(min_score=40, max_score=44, letter='E', grade_point='0.50')
        GradeBand.objects.create(min_score=0, max_score=39, letter='F', grade_point='0.00')

        cls.course1 = Course.objects.create(
            code='RMK101', title='Remark Course 1', credit_units=3, level=Level.LEVEL_100,
            department=cls.dept, programme=cls.programme, semester_name=SemesterName.FIRST,
        )
        cls.course2 = Course.objects.create(
            code='RMK102', title='Remark Course 2', credit_units=3, level=Level.LEVEL_100,
            department=cls.dept, programme=cls.programme, semester_name=SemesterName.FIRST,
        )
        cls.offering1 = CourseOffering.objects.create(course=cls.course1, semester=cls.semester, capacity=50)
        cls.offering2 = CourseOffering.objects.create(course=cls.course2, semester=cls.semester, capacity=50)

    def _student(self, suffix):
        student, _ = create_student(
            first_name='Test', last_name=f'Remark{suffix}', email=f'remark{suffix}@example.test',
            matric_number=f'RMK/2099/{suffix}', department=self.dept, level=Level.LEVEL_100,
            admission_session=self.session, programme=self.programme,
        )
        return student

    def _register(self, student, offering):
        CourseRegistration.objects.create(
            student=student, course_offering=offering, status=CourseRegistration.Status.REGISTERED,
        )

    def _grade(self, student, offering, total):
        Grade.objects.create(
            student=student, course_offering=offering,
            ca1_score=0, ca2_score=0, exam_score=total, status=Grade.Status.PUBLISHED,
        )

    def test_remark_classification_and_fail_sort_order(self):
        distinction = self._student('D')
        upper = self._student('U')
        lower = self._student('L')
        fail_by_gpa = self._student('G')
        fail_by_carryover = self._student('C')
        pending = self._student('P')

        for student in (distinction, upper, lower, fail_by_gpa, fail_by_carryover, pending):
            self._register(student, self.offering1)
            self._register(student, self.offering2)

        self._grade(distinction, self.offering1, 80)
        self._grade(distinction, self.offering2, 80)

        self._grade(upper, self.offering1, 65)
        self._grade(upper, self.offering2, 65)

        self._grade(lower, self.offering1, 55)
        self._grade(lower, self.offering2, 55)

        self._grade(fail_by_gpa, self.offering1, 45)
        self._grade(fail_by_gpa, self.offering2, 45)

        self._grade(fail_by_carryover, self.offering1, 20)   # F
        self._grade(fail_by_carryover, self.offering2, 80)   # A - GPA works out to 2.00, but the F forces Fail

        # pending: registered, never graded.

        sheet = get_master_broadsheet(programme=self.programme, semester=self.semester, level=Level.LEVEL_100)

        remarks_by_student = {row['student']: row['remark'] for row in sheet['rows']}
        self.assertEqual(remarks_by_student[distinction], 'Distinction')
        self.assertEqual(remarks_by_student[upper], 'Upper Credit')
        self.assertEqual(remarks_by_student[lower], 'Lower Credit')
        self.assertEqual(remarks_by_student[fail_by_gpa], 'Fail')
        self.assertEqual(remarks_by_student[fail_by_carryover], 'Fail')
        self.assertEqual(remarks_by_student[pending], 'Pending')

        # Fail rows sink to the bottom of the sheet.
        ordered_students = [row['student'] for row in sheet['rows']]
        fail_positions = [ordered_students.index(fail_by_gpa), ordered_students.index(fail_by_carryover)]
        non_fail_positions = [
            ordered_students.index(s) for s in (distinction, upper, lower, pending)
        ]
        self.assertTrue(max(non_fail_positions) < min(fail_positions))

    def test_broadsheet_cells_show_marks_not_letters(self):
        student = self._student('M')
        self._register(student, self.offering1)
        self._grade(student, self.offering1, 51)

        sheet = get_master_broadsheet(programme=self.programme, semester=self.semester, level=Level.LEVEL_100)

        row = next(r for r in sheet['rows'] if r['student'] == student)
        self.assertEqual(row['grades'][0].total_score, 51)

    def test_broadsheet_page_shows_serial_number_and_remark(self):
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.models import User
        from apps.core.constants import Role

        student = self._student('S')
        self._register(student, self.offering1)
        self._grade(student, self.offering1, 51)

        User.objects.create_user(username='exam.remark', password='exampass123', role=Role.EXAM_OFFICER)
        client = Client()
        self.assertTrue(client.login(username='exam.remark', password='exampass123'))

        response = client.get(reverse('results:master_broadsheet'), {
            'programme': str(self.programme.pk), 'level': Level.LEVEL_100, 'semester': str(self.semester.pk),
        })

        self.assertContains(response, 'S/N')
        self.assertContains(response, '>51<')
        self.assertNotContains(response, '>B<')
        self.assertContains(response, 'Lower Credit')


class PublishGradesBulkTests(TestCase):
    """FR-EXM: Select/Mark-all publish - many course offerings published
    in one action instead of one click per offering.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.students.services import create_student

        cls.session = AcademicSession.objects.create(name='2094/2095')
        cls.semester = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)
        cls.dept = Department.objects.create(name='Publish Department', code='PUB')

        cls.course1 = Course.objects.create(
            code='PUB101', title='Publish Course 1', credit_units=3, level=Level.LEVEL_100,
            department=cls.dept, semester_name=SemesterName.FIRST,
        )
        cls.course2 = Course.objects.create(
            code='PUB102', title='Publish Course 2', credit_units=3, level=Level.LEVEL_100,
            department=cls.dept, semester_name=SemesterName.FIRST,
        )
        cls.offering1 = CourseOffering.objects.create(course=cls.course1, semester=cls.semester, capacity=50)
        cls.offering2 = CourseOffering.objects.create(course=cls.course2, semester=cls.semester, capacity=50)

        cls.student, _ = create_student(
            first_name='Test', last_name='Publish', email='publish.test@example.test',
            matric_number='PUB/2099/1', department=cls.dept, level=Level.LEVEL_100,
            admission_session=cls.session,
        )

    def _grade(self, offering, *, status=Grade.Status.APPROVED, total=60):
        return Grade.objects.create(
            student=self.student, course_offering=offering,
            ca1_score=0, ca2_score=0, exam_score=total, status=status,
        )

    def test_publish_grades_for_offerings_publishes_only_approved_across_many_offerings(self):
        approved1 = self._grade(self.offering1)
        approved2 = self._grade(self.offering2)

        from apps.results import services

        count = services.publish_grades_for_offerings([self.offering1, self.offering2])

        self.assertEqual(count, 2)
        approved1.refresh_from_db()
        approved2.refresh_from_db()
        self.assertEqual(approved1.status, Grade.Status.PUBLISHED)
        self.assertEqual(approved2.status, Grade.Status.PUBLISHED)

    def test_publish_grades_for_offerings_leaves_non_approved_grades_untouched(self):
        from apps.results import services

        draft = Grade.objects.create(
            student=self.student, course_offering=self.offering1,
            ca1_score=0, ca2_score=0, exam_score=60, status=Grade.Status.DRAFT,
        )

        services.publish_grades_for_offerings([self.offering1])

        draft.refresh_from_db()
        self.assertEqual(draft.status, Grade.Status.DRAFT)

    def test_exam_officer_can_publish_several_selected_offerings_at_once(self):
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.models import User
        from apps.core.constants import Role

        grade1 = self._grade(self.offering1)
        grade2 = self._grade(self.offering2)

        User.objects.create_user(username='exam.publish', password='exampass123', role=Role.EXAM_OFFICER)
        client = Client()
        self.assertTrue(client.login(username='exam.publish', password='exampass123'))

        response = client.get(reverse('results:approved_grade_list'))
        self.assertContains(response, 'Select/Mark All')
        self.assertContains(response, 'name="offering_ids"')

        response = client.post(
            reverse('results:publish_grades_bulk'),
            {'offering_ids': [str(self.offering1.pk), str(self.offering2.pk)]},
            follow=True,
        )

        self.assertContains(response, 'Published 2 result(s) across 2 course offering(s)')
        grade1.refresh_from_db()
        grade2.refresh_from_db()
        self.assertEqual(grade1.status, Grade.Status.PUBLISHED)
        self.assertEqual(grade2.status, Grade.Status.PUBLISHED)

    def test_publishing_with_nothing_selected_warns_instead_of_crashing(self):
        from django.test import Client
        from django.urls import reverse

        from apps.accounts.models import User
        from apps.core.constants import Role

        User.objects.create_user(username='exam.empty', password='exampass123', role=Role.EXAM_OFFICER)
        client = Client()
        self.assertTrue(client.login(username='exam.empty', password='exampass123'))

        response = client.post(reverse('results:publish_grades_bulk'), {}, follow=True)

        self.assertContains(response, 'No course offerings were selected')
