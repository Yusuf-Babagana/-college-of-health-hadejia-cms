"""
Automated tests for the assign_student_programme management command's
safety guarantees: dry-run makes zero writes, an already-assigned
student is never silently moved, unknown codes fail clearly, and
re-running is idempotent.

Uses TestCase throughout - every test runs inside a transaction Django
rolls back afterwards, against Django's own separate test database.
"""
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.academics.models import AcademicSession
from apps.admissions.models import Programme
from apps.core.constants import Level
from apps.departments.models import Department
from apps.students.forms import StudentCreateForm
from apps.students.services import create_student


class AssignStudentProgrammeCommandTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2099/2100')
        cls.dept = Department.objects.create(name='Test Department', code='TSD')
        cls.programme_a = Programme.objects.create(
            name='Test Programme A', short_code='TPA', department=cls.dept, duration_levels=4,
        )
        cls.programme_b = Programme.objects.create(
            name='Test Programme B', short_code='TPB', department=cls.dept, duration_levels=4,
        )

    def _student(self, *, programme=None, suffix):
        student, _ = create_student(
            first_name='Test', last_name=f'Student{suffix}', email=f'test.assign{suffix}@example.test',
            matric_number=f'TSD/2099/{suffix}', department=self.dept, level=Level.LEVEL_100,
            admission_session=self.session, programme=programme,
        )
        return student

    def _run(self, *args):
        out = StringIO()
        call_command('assign_student_programme', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_makes_zero_writes(self):
        student = self._student(suffix='1')

        self._run('--matric', student.matric_number, '--programme', 'TPA', '--dry-run')

        student.refresh_from_db()
        self.assertIsNone(student.programme)

    def test_real_run_assigns_programme(self):
        student = self._student(suffix='2')

        self._run('--matric', student.matric_number, '--programme', 'TPA')

        student.refresh_from_db()
        self.assertEqual(student.programme, self.programme_a)

    def test_already_assigned_student_is_not_moved_without_force(self):
        student = self._student(programme=self.programme_a, suffix='3')

        self._run('--matric', student.matric_number, '--programme', 'TPB')

        student.refresh_from_db()
        self.assertEqual(
            student.programme, self.programme_a,
            'A student already on Programme A must not silently move to Programme B without --force.',
        )

    def test_force_flag_permits_reassignment(self):
        student = self._student(programme=self.programme_a, suffix='4')

        self._run('--matric', student.matric_number, '--programme', 'TPB', '--force')

        student.refresh_from_db()
        self.assertEqual(student.programme, self.programme_b)

    def test_idempotent_rerun_reports_no_changes(self):
        student = self._student(suffix='5')
        self._run('--matric', student.matric_number, '--programme', 'TPA')

        output = self._run('--matric', student.matric_number, '--programme', 'TPA')

        self.assertIn('No students need updating', output)
        student.refresh_from_db()
        self.assertEqual(student.programme, self.programme_a)

    def test_unknown_programme_code_raises_clear_error(self):
        student = self._student(suffix='6')

        with self.assertRaises(CommandError):
            self._run('--matric', student.matric_number, '--programme', 'DOES-NOT-EXIST')

        student.refresh_from_db()
        self.assertIsNone(student.programme)

    def test_unknown_matric_number_raises_clear_error(self):
        with self.assertRaises(CommandError):
            self._run('--matric', 'NOPE/9999/9999', '--programme', 'TPA')

    def test_no_filters_given_raises_clear_error(self):
        with self.assertRaises(CommandError):
            self._run('--programme', 'TPA')

    def test_department_level_filter_only_touches_matching_students(self):
        """Bulk filters must never reach beyond what was explicitly
        asked for - a student in a different department stays untouched.
        """
        other_dept = Department.objects.create(name='Other Department', code='OTH')
        in_scope = self._student(suffix='7')
        out_of_scope, _ = create_student(
            first_name='Test', last_name='OutOfScope', email='test.outofscope@example.test',
            matric_number='OTH/2099/1', department=other_dept, level=Level.LEVEL_100,
            admission_session=self.session,
        )

        self._run('--department', self.dept.code, '--level', '100', '--programme', 'TPA')

        in_scope.refresh_from_db()
        out_of_scope.refresh_from_db()
        self.assertEqual(in_scope.programme, self.programme_a)
        self.assertIsNone(out_of_scope.programme, 'A student outside the given department must not be touched.')


class MatricNumberFormatTests(TestCase):
    """The matric number is no longer restricted to the DEPT/YEAR/NNNN
    shape or auto-generated - the Registrar types in whatever number was
    assigned, and only uniqueness is enforced.
    """

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2050/2051')
        cls.dept = Department.objects.create(name='Free Format Department', code='FFD')

    def test_freeform_matric_number_is_accepted(self):
        student, _ = create_student(
            first_name='Free', last_name='Form', email='free.form@example.test',
            matric_number='STUDENT-0001', department=self.dept, level=Level.LEVEL_100,
            admission_session=self.session,
        )
        self.assertEqual(student.matric_number, 'STUDENT-0001')

    def test_matric_number_case_is_preserved_not_forced_uppercase(self):
        student, _ = create_student(
            first_name='Case', last_name='Kept', email='case.kept@example.test',
            matric_number='ffd-0002', department=self.dept, level=Level.LEVEL_100,
            admission_session=self.session,
        )
        self.assertEqual(student.matric_number, 'ffd-0002')

    def test_duplicate_matric_number_is_rejected_by_the_form(self):
        create_student(
            first_name='First', last_name='Student', email='first.student@example.test',
            matric_number='DUPLICATE-1', department=self.dept, level=Level.LEVEL_100,
            admission_session=self.session,
        )

        form = StudentCreateForm(data={
            'first_name': 'Second', 'last_name': 'Student', 'email': 'second.student@example.test',
            'phone_number': '', 'department': self.dept.pk, 'programme': '',
            'level': Level.LEVEL_100, 'admission_session': self.session.pk,
            'matric_number': 'DUPLICATE-1',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('matric_number', form.errors)

    def test_blank_matric_number_is_rejected_by_the_model(self):
        with self.assertRaises(ValidationError):
            create_student(
                first_name='No', last_name='Matric', email='no.matric@example.test',
                matric_number='', department=self.dept, level=Level.LEVEL_100,
                admission_session=self.session,
            )
