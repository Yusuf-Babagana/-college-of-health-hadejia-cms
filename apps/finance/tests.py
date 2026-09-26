"""
Automated tests for the finance app: FeeStructure's Programme/Semester
scoping (most-specific-wins, mirroring results.GradeBand) and the
student self-service "Generate Invoice" flow it feeds.

Uses TestCase throughout: every test runs inside a transaction Django
rolls back afterwards, against Django's own separate test database -
never the real development database, and nothing here persists past the
test run.
"""
from django.test import Client, TestCase
from django.urls import reverse

from apps.academics.models import AcademicSession, LevelSemesterState, Semester
from apps.admissions.models import Programme
from apps.core.constants import Level, SemesterName
from apps.departments.models import Department
from apps.finance import selectors, services
from apps.finance.forms import StudentInvoiceGenerateForm
from apps.finance.models import FeeStructure, FeeType, Invoice
from apps.students.services import create_student


class FeeStructureScopingTests(TestCase):
    """Most-specific-wins resolution: fully-specific (programme AND
    semester) beats programme-only, beats semester-only, beats the
    department/session-wide default (both blank).
    """

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2093/2094')
        cls.semester_first = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)
        cls.semester_second = Semester.objects.create(session=cls.session, name=SemesterName.SECOND)

        cls.dept = Department.objects.create(name='Fee Department', code='FEE')
        cls.programme_a = Programme.objects.create(
            name='Fee Programme A', short_code='FPA', department=cls.dept, duration_levels=4,
        )
        cls.programme_b = Programme.objects.create(
            name='Fee Programme B', short_code='FPB', department=cls.dept, duration_levels=4,
        )

        cls.tuition = FeeType.objects.create(name='Tuition')
        cls.practical = FeeType.objects.create(name='Practical Fee')

        cls.default_tuition = FeeStructure.objects.create(
            department=cls.dept, level=Level.LEVEL_100, session=cls.session, fee_type=cls.tuition,
            amount='1000.00',
        )
        cls.semester_specific_tuition = FeeStructure.objects.create(
            department=cls.dept, level=Level.LEVEL_100, session=cls.session, fee_type=cls.tuition,
            semester=cls.semester_first, amount='1200.00',
        )
        cls.programme_practical = FeeStructure.objects.create(
            department=cls.dept, level=Level.LEVEL_100, session=cls.session, fee_type=cls.practical,
            programme=cls.programme_a, amount='500.00',
        )

    def test_semester_specific_band_beats_the_default(self):
        match = selectors.get_fee_structure_for(
            department=self.dept, level=Level.LEVEL_100, session=self.session, fee_type=self.tuition,
            semester=self.semester_first,
        )
        self.assertEqual(match, self.semester_specific_tuition)

    def test_falls_back_to_default_when_no_scoped_match(self):
        match = selectors.get_fee_structure_for(
            department=self.dept, level=Level.LEVEL_100, session=self.session, fee_type=self.tuition,
            semester=self.semester_second,
        )
        self.assertEqual(match, self.default_tuition)

    def test_programme_specific_band_matches_for_that_programme(self):
        match = selectors.get_fee_structure_for(
            department=self.dept, level=Level.LEVEL_100, session=self.session, fee_type=self.practical,
            programme=self.programme_a, semester=self.semester_first,
        )
        self.assertEqual(match, self.programme_practical)

    def test_no_match_for_a_different_programme_with_no_fallback_defined(self):
        match = selectors.get_fee_structure_for(
            department=self.dept, level=Level.LEVEL_100, session=self.session, fee_type=self.practical,
            programme=self.programme_b, semester=self.semester_first,
        )
        self.assertIsNone(match)


class StudentInvoiceGenerationTests(TestCase):
    """FR-FIN: student self-service invoice generation - Programme +
    Semester feed the most-specific-wins FeeStructure lookup above.
    """

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2092/2093')
        cls.semester_first = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=cls.semester_first)

        cls.dept = Department.objects.create(name='Invoice Department', code='INV')
        cls.programme = Programme.objects.create(
            name='Invoice Programme', short_code='INVP', department=cls.dept, duration_levels=4,
        )

        cls.tuition = FeeType.objects.create(name='Invoice Tuition')
        cls.practical = FeeType.objects.create(name='Invoice Practical')

        FeeStructure.objects.create(
            department=cls.dept, level=Level.LEVEL_100, session=cls.session, fee_type=cls.tuition,
            semester=cls.semester_first, amount='1200.00',
        )
        FeeStructure.objects.create(
            department=cls.dept, level=Level.LEVEL_100, session=cls.session, fee_type=cls.practical,
            programme=cls.programme, amount='500.00',
        )

        cls.student, cls.student_password = create_student(
            first_name='Test', last_name='Invoice', email='test.invoice@example.test',
            matric_number='INV/2099/1', department=cls.dept, level=Level.LEVEL_100,
            admission_session=cls.session, programme=cls.programme,
        )
        cls.student.user.must_change_password = False
        cls.student.user.save(update_fields=['must_change_password'])

    def test_generate_invoices_for_student_creates_one_per_matching_fee_type(self):
        created = services.generate_invoices_for_student(
            student=self.student, programme=self.programme, semester=self.semester_first,
        )

        self.assertEqual(len(created), 2)
        amounts = sorted(invoice.amount_due for invoice in created)
        self.assertEqual([str(a) for a in amounts], ['500.00', '1200.00'])

    def test_generate_invoices_is_idempotent(self):
        services.generate_invoices_for_student(
            student=self.student, programme=self.programme, semester=self.semester_first,
        )

        second_call = services.generate_invoices_for_student(
            student=self.student, programme=self.programme, semester=self.semester_first,
        )

        self.assertEqual(second_call, [])
        self.assertEqual(Invoice.objects.filter(student=self.student).count(), 2)

    def test_form_scopes_programme_to_the_students_department_and_defaults_it(self):
        form = StudentInvoiceGenerateForm(student=self.student)

        self.assertIn(self.programme, form.fields['programme'].queryset)
        self.assertEqual(form.fields['programme'].initial, self.programme.pk)
        self.assertIn(self.semester_first, form.fields['semester'].queryset)
        self.assertEqual(form.fields['semester'].initial, self.semester_first.pk)

    def test_student_can_generate_an_invoice_through_the_view(self):
        client = Client()
        client.force_login(self.student.user)

        response = client.get(reverse('finance:my_invoices'))
        self.assertContains(response, 'Generate Invoice')

        response = client.post(
            reverse('finance:generate_my_invoice'),
            {'programme': str(self.programme.pk), 'semester': str(self.semester_first.pk)},
            follow=True,
        )

        self.assertContains(response, 'Generated 2 invoice(s)')
        self.assertEqual(Invoice.objects.filter(student=self.student).count(), 2)

    def test_generating_again_with_nothing_new_informs_instead_of_erroring(self):
        client = Client()
        client.force_login(self.student.user)

        client.post(
            reverse('finance:generate_my_invoice'),
            {'programme': str(self.programme.pk), 'semester': str(self.semester_first.pk)},
        )
        response = client.post(
            reverse('finance:generate_my_invoice'),
            {'programme': str(self.programme.pk), 'semester': str(self.semester_first.pk)},
            follow=True,
        )

        self.assertContains(response, 'No new invoices')

    def test_my_invoices_page_shows_a_message_when_no_semester_is_current(self):
        LevelSemesterState.objects.filter(level=Level.LEVEL_100).delete()

        client = Client()
        client.force_login(self.student.user)
        response = client.get(reverse('finance:my_invoices'))

        self.assertContains(response, 'No semester is currently running for your level')
