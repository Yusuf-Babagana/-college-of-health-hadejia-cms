"""
Automated tests for course/programme eligibility. Uses TestCase, so
every test runs inside a transaction that Django rolls back afterwards -
nothing here ever touches the real development database, and none of
this data survives past the test run.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.admissions.models import Programme
from apps.core.constants import Level, SemesterName
from apps.courses.models import Course, CourseOffering
from apps.courses.selectors import get_course_offerings_for_programme
from apps.departments.models import Department


class GetCourseOfferingsForProgrammeTests(TestCase):
    """Direct unit tests of the shared "which courses belong to this
    Programme" rule extracted from get_master_broadsheet's old inline
    duplicate - this is now the single authoritative definition used by
    the Master Broadsheet's column stage.
    """

    @classmethod
    def setUpTestData(cls):
        cls.session = cls._make_session()
        cls.semester = cls._make_semester(cls.session)

        cls.dept = Department.objects.create(name='Test Department', code='TSD')
        cls.gst_dept = Department.objects.create(
            name='Test General Studies', code='TGS', is_general_studies=True,
        )

        cls.programme_a = Programme.objects.create(
            name='Test Programme A', short_code='TPA', department=cls.dept, duration_levels=4,
        )
        cls.programme_b = Programme.objects.create(
            name='Test Programme B', short_code='TPB', department=cls.dept, duration_levels=4,
        )

    @staticmethod
    def _make_session():
        from apps.academics.models import AcademicSession
        return AcademicSession.objects.create(name='2099/2100')

    @staticmethod
    def _make_semester(session):
        from apps.academics.models import Semester
        return Semester.objects.create(session=session, name=SemesterName.FIRST)

    def _offering(self, course):
        return CourseOffering.objects.create(course=course, semester=self.semester, capacity=50)

    def _base_qs(self):
        return CourseOffering.objects.filter(course__level=Level.LEVEL_100, semester=self.semester)

    def test_course_with_matching_primary_programme_is_included(self):
        course = Course.objects.create(
            code='TST101', title='Primary match', credit_units=2, level=Level.LEVEL_100,
            department=self.dept, programme=self.programme_a, semester_name=SemesterName.FIRST,
        )
        offering = self._offering(course)

        result = get_course_offerings_for_programme(self._base_qs(), self.programme_a)
        self.assertIn(offering, result)

    def test_course_with_different_primary_programme_is_excluded(self):
        course = Course.objects.create(
            code='TST102', title='Different primary', credit_units=2, level=Level.LEVEL_100,
            department=self.dept, programme=self.programme_a, semester_name=SemesterName.FIRST,
        )
        offering = self._offering(course)

        result = get_course_offerings_for_programme(self._base_qs(), self.programme_b)
        self.assertNotIn(offering, result)

    def test_course_cross_listed_via_eligible_programmes_is_included_for_both(self):
        course = Course.objects.create(
            code='TST103', title='Shared', credit_units=2, level=Level.LEVEL_100,
            department=self.dept, programme=self.programme_a, semester_name=SemesterName.FIRST,
        )
        course.eligible_programmes.set([self.programme_a, self.programme_b])
        offering = self._offering(course)

        result_a = get_course_offerings_for_programme(self._base_qs(), self.programme_a)
        result_b = get_course_offerings_for_programme(self._base_qs(), self.programme_b)
        self.assertIn(offering, result_a)
        self.assertIn(offering, result_b)

    def test_untagged_general_studies_course_is_blanket_available(self):
        course = Course.objects.create(
            code='TST104', title='Blanket GST', credit_units=2, level=Level.LEVEL_100,
            department=self.gst_dept, semester_name=SemesterName.FIRST,
        )
        offering = self._offering(course)

        result_a = get_course_offerings_for_programme(self._base_qs(), self.programme_a)
        result_b = get_course_offerings_for_programme(self._base_qs(), self.programme_b)
        self.assertIn(offering, result_a)
        self.assertIn(offering, result_b)

    def test_general_studies_course_explicitly_narrowed_does_not_leak(self):
        course = Course.objects.create(
            code='TST105', title='Narrowed GST', credit_units=2, level=Level.LEVEL_100,
            department=self.gst_dept, semester_name=SemesterName.FIRST,
        )
        course.eligible_programmes.set([self.programme_a])
        offering = self._offering(course)

        result_a = get_course_offerings_for_programme(self._base_qs(), self.programme_a)
        result_b = get_course_offerings_for_programme(self._base_qs(), self.programme_b)
        self.assertIn(offering, result_a)
        self.assertNotIn(offering, result_b)

    def test_untagged_ordinary_department_course_is_excluded_everywhere(self):
        """A course with no Programme/eligible_programmes under a
        NON-General-Studies department belongs to nobody until tagged -
        this is the exact CHE113/ANP111 situation from the live bug
        report, reproduced with disposable test-only data.
        """
        course = Course.objects.create(
            code='TST106', title='Untagged, ordinary department', credit_units=2, level=Level.LEVEL_100,
            department=self.dept, semester_name=SemesterName.FIRST,
        )
        offering = self._offering(course)

        result_a = get_course_offerings_for_programme(self._base_qs(), self.programme_a)
        result_b = get_course_offerings_for_programme(self._base_qs(), self.programme_b)
        self.assertNotIn(offering, result_a)
        self.assertNotIn(offering, result_b)


class TagCourseProgrammeCommandTests(TestCase):
    """Safety tests for the tag_course_programme management command:
    dry-run makes zero writes (both the FK and the M2M change), unknown
    codes fail clearly, and re-running is idempotent.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Test Department', code='TSD')
        cls.other_dept = Department.objects.create(name='Other Department', code='OTH')
        cls.programme_a = Programme.objects.create(
            name='Test Programme A', short_code='TPA', department=cls.dept, duration_levels=4,
        )
        cls.programme_b = Programme.objects.create(
            name='Test Programme B', short_code='TPB', department=cls.dept, duration_levels=4,
        )

    def setUp(self):
        self.course = Course.objects.create(
            code='TST301', title='Untagged course', credit_units=2, level=Level.LEVEL_100,
            department=self.dept, semester_name=SemesterName.FIRST,
        )

    def _run(self, *args):
        out = StringIO()
        call_command('tag_course_programme', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_makes_zero_writes_fk_and_m2m(self):
        self._run(self.course.code, '--programme', 'TPA', '--eligible', 'TPA', '--eligible', 'TPB', '--dry-run')

        self.course.refresh_from_db()
        self.assertIsNone(self.course.programme)
        self.assertEqual(list(self.course.eligible_programmes.all()), [])

    def test_real_run_sets_programme_and_eligible_programmes(self):
        self._run(self.course.code, '--programme', 'TPA', '--eligible', 'TPA', '--eligible', 'TPB')

        self.course.refresh_from_db()
        self.assertEqual(self.course.programme, self.programme_a)
        self.assertCountEqual(self.course.eligible_programmes.all(), [self.programme_a, self.programme_b])

    def test_department_reassignment(self):
        self._run(self.course.code, '--department', 'OTH')

        self.course.refresh_from_db()
        self.assertEqual(self.course.department, self.other_dept)

    def test_idempotent_rerun_reports_no_changes(self):
        self._run(self.course.code, '--programme', 'TPA', '--eligible', 'TPA')

        output = self._run(self.course.code, '--programme', 'TPA', '--eligible', 'TPA')

        self.assertIn('No changes needed', output)

    def test_unknown_course_code_raises_clear_error(self):
        with self.assertRaises(CommandError):
            self._run('DOES-NOT-EXIST', '--programme', 'TPA')

    def test_unknown_programme_code_raises_clear_error(self):
        with self.assertRaises(CommandError):
            self._run(self.course.code, '--programme', 'DOES-NOT-EXIST')

        self.course.refresh_from_db()
        self.assertIsNone(self.course.programme)

    def test_level_outside_programme_duration_is_rejected(self):
        """Course.clean()'s level/duration_levels validation must still
        fire when this command sets a Programme, not be silently
        bypassed - a 2-level Certificate can't own a Level 300 course.
        """
        short_programme = Programme.objects.create(
            name='Test Short Programme', short_code='TSHORT', department=self.dept, duration_levels=2,
        )
        course_300 = Course.objects.create(
            code='TST302', title='Level 300 course', credit_units=2, level=Level.LEVEL_300,
            department=self.dept, semester_name=SemesterName.FIRST,
        )

        with self.assertRaises(CommandError):
            self._run(course_300.code, '--programme', short_programme.short_code)

        course_300.refresh_from_db()
        self.assertIsNone(course_300.programme)
