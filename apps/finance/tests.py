"""
Automated tests for the finance app: FeeStructure's Programme/Semester
scoping (most-specific-wins, mirroring results.GradeBand) and the
program-based invoice generation and isolated per-invoice payment.

Uses TestCase throughout: every test runs inside a transaction Django
rolls back afterwards, against Django's own separate test database -
never the real development database, and nothing here persists past the
test run.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.academics.models import AcademicSession, LevelSemesterState, Semester
from apps.admissions.models import Programme
from apps.core.constants import Level, Role, SemesterName
from apps.departments.models import Department
from apps.finance import selectors, services
from apps.finance.models import FeeStructure, FeeType, Invoice, Payment
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


class ProgramInvoiceTestBase(TestCase):
    """Two programmes in one department; Program A / 200 Level / First
    Semester / 2096-2097 is the invoice under test."""

    @classmethod
    def setUpTestData(cls):
        cls.session = AcademicSession.objects.create(name='2096/2097')
        cls.other_session = AcademicSession.objects.create(name='2097/2098')
        cls.sem_first = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)
        cls.sem_other = Semester.objects.create(session=cls.other_session, name=SemesterName.FIRST)
        LevelSemesterState.objects.create(level=Level.LEVEL_200, semester=cls.sem_first)

        cls.dept = Department.objects.create(name='Nursing Dept', code='NUR')
        cls.prog_a = Programme.objects.create(name='Nursing', short_code='NUR', department=cls.dept, duration_levels=4)
        cls.prog_b = Programme.objects.create(name='Midwifery', short_code='MID', department=cls.dept, duration_levels=4)
        cls.fee_type = FeeType.objects.create(name='School Fees')
        cls.bursar = get_user_model().objects.create_user(username='bursar1', password='x', role=Role.BURSAR)

        cls.a1 = cls.make_student('a1', cls.prog_a, Level.LEVEL_200)
        cls.a2 = cls.make_student('a2', cls.prog_a, Level.LEVEL_200)
        cls.b1 = cls.make_student('b1', cls.prog_b, Level.LEVEL_200)
        cls.a_l100 = cls.make_student('a100', cls.prog_a, Level.LEVEL_100)

    @classmethod
    def make_student(cls, tag, programme, level):
        student, _ = create_student(
            first_name='T', last_name=tag, email=f'{tag}@example.test', matric_number=f'NUR/2099/{tag}',
            department=cls.dept, level=level, admission_session=cls.session, programme=programme,
        )
        student.user.must_change_password = False
        student.user.save(update_fields=['must_change_password'])
        return student

    def make_fee(self, **overrides):
        values = dict(
            fee_type=self.fee_type, department=self.dept, programme=self.prog_a, level=Level.LEVEL_200,
            session=self.session, semester=self.sem_first, amount=Decimal('50000.00'),
            description='First semester school fees',
        )
        values.update(overrides)
        return FeeStructure.objects.create(**values)

    def login(self, student):
        client = Client()
        client.force_login(student.user)
        return client


class ProgramInvoiceVisibilityTests(ProgramInvoiceTestBase):
    def test_admin_creates_invoice_for_program_and_eligible_students_get_it(self):
        client = Client()
        client.force_login(self.bursar)
        response = client.post(reverse('finance:fee_structure_create'), {
            'programme': self.prog_a.pk, 'department': self.dept.pk, 'level': 200,
            'session': self.session.pk, 'semester': self.sem_first.pk, 'fee_type': self.fee_type.pk,
            'description': 'First semester school fees', 'amount': '50000.00',
            'due_date': '2099-01-31', 'is_published': 'on',
        }, follow=True)
        self.assertContains(response, '2 new invoice(s) generated')
        invoices = Invoice.objects.all()
        self.assertEqual({i.student_id for i in invoices}, {self.a1.pk, self.a2.pk})
        self.assertTrue(all(i.invoice_number for i in invoices))
        self.assertEqual({str(i.due_date) for i in invoices}, {'2099-01-31'})

    def test_program_is_required_on_new_fee(self):
        client = Client()
        client.force_login(self.bursar)
        response = client.post(reverse('finance:fee_structure_create'), {
            'department': self.dept.pk, 'level': 200, 'session': self.session.pk,
            'fee_type': self.fee_type.pk, 'amount': '1000', 'is_published': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FeeStructure.objects.exists())

    def test_eligible_student_sees_invoice_with_correct_amount(self):
        self.make_fee()
        response = self.login(self.a1).get(reverse('finance:my_invoices'))
        self.assertContains(response, 'First semester school fees')
        self.assertEqual(Invoice.objects.get(student=self.a1).amount_due, Decimal('50000.00'))

    def test_other_program_student_does_not_see_it(self):
        self.make_fee()
        response = self.login(self.b1).get(reverse('finance:my_invoices'))
        self.assertNotContains(response, 'First semester school fees')
        self.assertFalse(Invoice.objects.filter(student=self.b1).exists())

    def test_other_level_student_does_not_see_it(self):
        self.make_fee()
        self.login(self.a_l100).get(reverse('finance:my_invoices'))
        self.assertFalse(Invoice.objects.filter(student=self.a_l100).exists())

    def test_wrong_session_or_semester_not_eligible(self):
        fee = self.make_fee(session=self.other_session, semester=self.sem_other)
        self.assertFalse(selectors.get_eligible_students(fee).exists())
        self.login(self.a1).get(reverse('finance:my_invoices'))
        self.assertFalse(Invoice.objects.filter(student=self.a1).exists())

    def test_unpublished_fee_generates_nothing_and_is_hidden(self):
        fee = self.make_fee(is_published=False)
        self.login(self.a1).get(reverse('finance:my_invoices'))
        self.assertFalse(Invoice.objects.exists())
        with self.assertRaises(ValidationError):
            services.bulk_generate_invoices(fee_structure=fee)

    def test_department_wide_fee_covers_every_programme(self):
        self.make_fee(programme=None)
        for student in (self.a1, self.b1):
            self.login(student).get(reverse('finance:my_invoices'))
        self.assertEqual(Invoice.objects.count(), 2)

    def test_program_specific_fee_wins_over_department_wide(self):
        self.make_fee(programme=None, amount=Decimal('10000.00'))
        self.make_fee(amount=Decimal('50000.00'))
        self.login(self.a1).get(reverse('finance:my_invoices'))
        self.login(self.b1).get(reverse('finance:my_invoices'))
        self.assertEqual(Invoice.objects.get(student=self.a1).amount_due, Decimal('50000.00'))
        self.assertEqual(Invoice.objects.get(student=self.b1).amount_due, Decimal('10000.00'))
        self.assertEqual(Invoice.objects.filter(student=self.a1).count(), 1)

    def test_student_cannot_open_another_students_invoice(self):
        self.make_fee()
        self.login(self.a2).get(reverse('finance:my_invoices'))
        others = Invoice.objects.get(student=self.a2)
        response = self.login(self.a1).get(reverse('finance:initiate_payment', args=[others.pk]), follow=True)
        self.assertContains(response, 'Invoice not found')

    def test_student_self_service_generation_is_gone(self):
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse('finance:generate_my_invoice')

    def test_eligible_students_screen_and_report_render(self):
        fee = self.make_fee()
        services.bulk_generate_invoices(fee_structure=fee)
        client = Client()
        client.force_login(self.bursar)
        response = client.get(reverse('finance:fee_structure_students', args=[fee.pk]))
        self.assertContains(response, self.a1.matric_number)
        self.assertNotContains(response, self.b1.matric_number)
        response = client.get(reverse('finance:programme_report'))
        self.assertContains(response, 'Nursing')
        response = client.get(reverse('finance:invoice_list'), {'programme': self.prog_a.pk})
        self.assertEqual(len(response.context['invoices']), 2)
        response = client.get(reverse('finance:invoice_list'), {'programme': self.prog_b.pk})
        self.assertEqual(len(response.context['invoices']), 0)


class IsolatedInvoicePaymentTests(ProgramInvoiceTestBase):
    def setUp(self):
        self.fee = self.make_fee()
        self.invoice = services.generate_invoice(student=self.a1, fee_structure=self.fee)

    def test_online_payment_charges_only_this_invoice_not_arrears(self):
        old_fee = self.make_fee(
            fee_type=FeeType.objects.create(name='Old Debt'), amount=Decimal('20000.00'),
        )
        arrears = services.generate_invoice(student=self.a1, fee_structure=old_fee)
        with mock.patch('apps.finance.paystack.initialize_transaction',
                        return_value={'authorization_url': 'https://pay.test/x'}) as init:
            services.initiate_online_payment(invoice=self.invoice, email='a1@example.test', callback_url='http://t/cb')
        self.assertEqual(init.call_args.kwargs['amount_kobo'], 5_000_000)  # 50,000 only, not 70,000
        payment = Payment.objects.get(invoice=self.invoice)
        self.assertEqual(payment.amount, Decimal('50000.00'))
        self.assertFalse(Payment.objects.filter(invoice=arrears).exists())

    def test_payment_page_shows_only_invoice_amount(self):
        response = self.login(self.a1).get(reverse('finance:initiate_payment', args=[self.invoice.pk]))
        self.assertContains(response, '50,000')
        self.assertNotContains(response, 'part payment')

    def test_part_payment_amount_rejected(self):
        with self.assertRaises(ValidationError):
            services.initiate_online_payment(
                invoice=self.invoice, email='a1@example.test', callback_url='http://t/cb', amount=Decimal('100'),
            )

    def _pending(self, invoice=None):
        invoice = invoice or self.invoice
        return Payment.objects.create(
            invoice=invoice, amount=invoice.balance, method=Payment.Method.ONLINE,
            reference=f'PSK-T{Payment.objects.count()}', status=Payment.Status.PENDING,
        )

    def test_verified_payment_settles_only_its_invoice(self):
        other_fee = self.make_fee(fee_type=FeeType.objects.create(name='Other'), amount=Decimal('9000.00'))
        other = services.generate_invoice(student=self.a1, fee_structure=other_fee)
        payment = self._pending()
        with mock.patch('apps.finance.paystack.verify_transaction', return_value={'status': 'success', 'amount': 5_000_000}):
            services.verify_online_payment(payment.reference)
        self.invoice.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(other.amount_paid, Decimal('0'))
        self.assertEqual(other.status, Invoice.Status.PENDING)

    def test_verification_is_idempotent(self):
        payment = self._pending()
        with mock.patch('apps.finance.paystack.verify_transaction', return_value={'status': 'success', 'amount': 5_000_000}):
            services.verify_online_payment(payment.reference)
            services.verify_online_payment(payment.reference)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('50000.00'))

    def test_gateway_amount_mismatch_is_not_credited(self):
        payment = self._pending()
        with mock.patch('apps.finance.paystack.verify_transaction', return_value={'status': 'success', 'amount': 100}):
            result = services.verify_online_payment(payment.reference)
        self.invoice.refresh_from_db()
        self.assertEqual(result.status, Payment.Status.FAILED)
        self.assertEqual(self.invoice.amount_paid, Decimal('0'))

    def test_second_payment_after_settlement_is_not_double_credited(self):
        first, second = self._pending(), self._pending()
        with mock.patch('apps.finance.paystack.verify_transaction', return_value={'status': 'success', 'amount': 5_000_000}):
            services.verify_online_payment(first.reference)
            result = services.verify_online_payment(second.reference)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('50000.00'))
        self.assertEqual(result.status, Payment.Status.FAILED)
        self.assertIn('refund', result.notes)

    def test_paid_invoice_cannot_be_paid_again(self):
        services.record_offline_payment(
            invoice=self.invoice, amount=Decimal('50000.00'), reference='TELLER-1', notes='', recorded_by=self.bursar,
        )
        with self.assertRaises(ValidationError):
            services.initiate_online_payment(invoice=self.invoice, email='a1@example.test', callback_url='http://t/cb')
        with self.assertRaises(ValidationError):
            services.record_offline_payment(
                invoice=self.invoice, amount=Decimal('1.00'), reference='TELLER-2', notes='', recorded_by=self.bursar,
            )

    def test_unpublished_invoice_is_not_payable(self):
        self.fee.is_published = False
        self.fee.save(update_fields=['is_published'])
        with self.assertRaises(ValidationError):
            services.initiate_online_payment(invoice=self.invoice, email='a1@example.test', callback_url='http://t/cb')

    def test_invoice_numbers_are_unique(self):
        second = services.generate_invoice(student=self.a2, fee_structure=self.fee)
        self.assertNotEqual(self.invoice.invoice_number, second.invoice_number)
        self.assertTrue(self.invoice.invoice_number.startswith('INV-'))
