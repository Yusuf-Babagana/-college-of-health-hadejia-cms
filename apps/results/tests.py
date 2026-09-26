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
from django.test import TestCase

from apps.academics.models import AcademicSession, Semester
from apps.admissions.models import Programme
from apps.core.constants import Level, SemesterName
from apps.courses.models import Course, CourseOffering, CourseRegistration
from apps.departments.models import Department
from apps.results.selectors import get_master_broadsheet
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
            department=self.dept, level=level, admission_session=self.session, programme=programme,
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
