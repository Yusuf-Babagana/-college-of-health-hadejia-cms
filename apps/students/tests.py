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


class StudentPromotionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from apps.core.constants import Role

        cls.session = AcademicSession.objects.create(name='2096/2097')
        cls.dept = Department.objects.create(name='Nursing Dept', code='NUR')
        cls.prog = Programme.objects.create(name='Certificate', short_code='CRT', department=cls.dept, duration_levels=2)
        cls.registrar = get_user_model().objects.create_user(username='reg', password='x', role=Role.REGISTRAR)
        cls.student, _ = create_student(
            first_name='T', last_name='S', email='s@example.test', matric_number='NUR/1',
            department=cls.dept, level=Level.LEVEL_100, admission_session=cls.session, programme=cls.prog,
        )

    def promote(self):
        from django.test import Client
        from django.urls import reverse

        client = Client()
        client.force_login(self.registrar)
        return client.post(reverse('students:student_promote', args=[self.student.pk]), follow=True)

    def test_promote_moves_up_one_level_and_persists(self):
        response = self.promote()
        self.student.refresh_from_db()
        self.assertEqual(self.student.level, Level.LEVEL_200)
        self.assertContains(response, 'promoted from 100 Level to 200 Level')

    def test_cannot_promote_past_programme_final_level(self):
        self.promote()
        response = self.promote()
        self.student.refresh_from_db()
        self.assertEqual(self.student.level, Level.LEVEL_200)
        self.assertContains(response, 'already at the final level')

    def test_only_active_students_can_be_promoted(self):
        from apps.students.models import Student
        from apps.students.services import promote_student, update_student_status

        update_student_status(self.student, Student.Status.SUSPENDED)
        with self.assertRaises(ValidationError):
            promote_student(self.student)

    def test_promote_is_post_only_and_role_protected(self):
        from django.test import Client
        from django.urls import reverse

        client = Client()
        client.force_login(self.registrar)
        self.assertEqual(client.get(reverse('students:student_promote', args=[self.student.pk])).status_code, 405)
        student_client = Client()
        student_client.force_login(self.student.user)
        student_client.post(reverse('students:student_promote', args=[self.student.pk]))
        self.student.refresh_from_db()
        self.assertEqual(self.student.level, Level.LEVEL_100)


class BulkPromotionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from apps.core.constants import Role

        cls.session = AcademicSession.objects.create(name='2096/2097')
        cls.dept = Department.objects.create(name='Nursing Dept', code='NUR')
        cls.four = Programme.objects.create(name='Diploma', short_code='DIP', department=cls.dept, duration_levels=4)
        cls.two = Programme.objects.create(name='Certificate', short_code='CRT', department=cls.dept, duration_levels=2)
        User = get_user_model()
        cls.super_admin = User.objects.create_superuser(username='sa', password='x', email='sa@example.test')
        cls.super_admin.role = Role.SUPER_ADMIN
        cls.super_admin.save()
        cls.registrar = User.objects.create_user(username='reg', password='x', role=Role.REGISTRAR)

        def make(tag, programme, level):
            student, _ = create_student(
                first_name='T', last_name=tag, email=f'{tag}@example.test', matric_number=f'NUR/{tag}',
                department=cls.dept, level=level, admission_session=cls.session, programme=programme,
            )
            return student

        cls.d1, cls.d2 = make('d1', cls.four, Level.LEVEL_100), make('d2', cls.four, Level.LEVEL_100)
        cls.c1 = make('c1', cls.two, Level.LEVEL_100)
        cls.c_final = make('cf', cls.two, Level.LEVEL_200)   # final level of a 2-level programme
        cls.d_other = make('d3', cls.four, Level.LEVEL_300)  # different level: untouched

    def post(self, user, **data):
        from django.test import Client
        from django.urls import reverse
        client = Client()
        client.force_login(user)
        return client.post(reverse('students:bulk_promote'), data, follow=True)

    def level(self, student):
        student.refresh_from_db()
        return student.level

    def test_preview_changes_nothing_and_shows_counts(self):
        response = self.post(self.super_admin, level=100, programme='')
        self.assertContains(response, 'Please confirm')
        self.assertContains(response, 'Yes, promote 3 student(s)')
        self.assertEqual(self.level(self.d1), Level.LEVEL_100)

    def test_confirm_promotes_everyone_at_the_level_only(self):
        response = self.post(self.super_admin, level=100, programme='', confirm='1')
        self.assertContains(response, 'Promoted 3 student(s)')
        for student in (self.d1, self.d2, self.c1):
            self.assertEqual(self.level(student), Level.LEVEL_200)
        self.assertEqual(self.level(self.d_other), Level.LEVEL_300)
        self.assertEqual(self.level(self.c_final), Level.LEVEL_200)

    def test_can_be_scoped_to_one_programme(self):
        self.post(self.super_admin, level=100, programme=self.four.pk, confirm='1')
        self.assertEqual(self.level(self.d1), Level.LEVEL_200)
        self.assertEqual(self.level(self.c1), Level.LEVEL_100)

    def test_students_at_final_level_are_skipped_not_promoted(self):
        response = self.post(self.super_admin, level=200, programme=self.two.pk, confirm='1')
        self.assertContains(response, 'Promoted 0')
        self.assertContains(response, '1 at their final level')
        self.assertEqual(self.level(self.c_final), Level.LEVEL_200)

    def test_only_active_students_are_promoted(self):
        from apps.students.models import Student
        from apps.students.services import update_student_status
        update_student_status(self.d2, Student.Status.SUSPENDED)
        self.post(self.super_admin, level=100, programme=self.four.pk, confirm='1')
        self.assertEqual(self.level(self.d1), Level.LEVEL_200)
        self.assertEqual(self.level(self.d2), Level.LEVEL_100)

    def test_invalid_programme_level_pair_rejected(self):
        response = self.post(self.super_admin, level=300, programme=self.two.pk, confirm='1')
        self.assertContains(response, 'does not have a')
        self.assertEqual(self.level(self.d_other), Level.LEVEL_300)

    def test_super_admin_only(self):
        from django.urls import reverse
        self.post(self.registrar, level=100, programme='', confirm='1')
        self.assertEqual(self.level(self.d1), Level.LEVEL_100)

    def test_button_is_on_the_super_admin_dashboard(self):
        from django.test import Client
        from django.urls import reverse
        client = Client()
        client.force_login(self.super_admin)
        response = client.get(reverse('dashboard:super_admin'))
        self.assertContains(response, reverse('students:bulk_promote'))
        self.assertContains(response, 'Promote Students')


class AdminPromoteActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.session = AcademicSession.objects.create(name='2096/2097')
        cls.dept = Department.objects.create(name='Nursing Dept', code='NUR')
        cls.two = Programme.objects.create(name='Certificate', short_code='CRT', department=cls.dept, duration_levels=2)
        # a Django superuser with NO role - the account that only ever sees /admin/
        cls.admin_user = get_user_model().objects.create_superuser(username='su', password='x', email='su@example.test')

        def make(tag, level):
            student, _ = create_student(
                first_name='T', last_name=tag, email=f'{tag}@example.test', matric_number=f'NUR/{tag}',
                department=cls.dept, level=level, admission_session=cls.session, programme=cls.two,
            )
            return student

        cls.a, cls.b = make('a', Level.LEVEL_100), make('b', Level.LEVEL_100)
        cls.final = make('f', Level.LEVEL_200)

    def run_action(self, students, **extra):
        from django.test import Client
        from django.urls import reverse
        client = Client()
        client.force_login(self.admin_user)
        data = {'action': 'promote_selected', '_selected_action': [str(s.pk) for s in students], **extra}
        return client.post(reverse('admin:students_student_changelist'), data, follow=True)

    def level(self, student):
        student.refresh_from_db()
        return student.level

    def test_action_is_listed_in_the_admin(self):
        from django.test import Client
        from django.urls import reverse
        client = Client()
        client.force_login(self.admin_user)
        response = client.get(reverse('admin:students_student_changelist'))
        self.assertContains(response, 'Promote selected students to the next level')

    def test_first_step_previews_and_changes_nothing(self):
        response = self.run_action([self.a, self.b, self.final])
        self.assertContains(response, 'will move up one level')
        self.assertContains(response, 'Yes, promote 2 student(s)')
        self.assertEqual(self.level(self.a), Level.LEVEL_100)

    def test_confirm_promotes_and_skips_final_level_students(self):
        response = self.run_action([self.a, self.b, self.final], confirm='1')
        self.assertContains(response, 'Promoted 2 student(s)')
        self.assertEqual(self.level(self.a), Level.LEVEL_200)
        self.assertEqual(self.level(self.b), Level.LEVEL_200)
        self.assertEqual(self.level(self.final), Level.LEVEL_200)

    def test_inactive_students_are_skipped(self):
        from apps.students.models import Student
        from apps.students.services import update_student_status
        update_student_status(self.b, Student.Status.SUSPENDED)
        self.run_action([self.a, self.b], confirm='1')
        self.assertEqual(self.level(self.a), Level.LEVEL_200)
        self.assertEqual(self.level(self.b), Level.LEVEL_100)


import shutil
import tempfile
from datetime import date, timedelta
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.students.models import Student

_MEDIA = tempfile.mkdtemp(prefix='cohst-test-media-')


def _image_bytes(size=(1200, 1500), fmt='PNG', mode='RGB', color=(30, 90, 200)):
    from PIL import Image
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, fmt)
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=_MEDIA)
class StudentProfileTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from apps.core.constants import Role

        cls.session = AcademicSession.objects.create(name='2096/2097')
        cls.dept = Department.objects.create(name='Nursing Dept', code='NUR')
        cls.student, _ = create_student(
            first_name='Amina', last_name='Bello', email='amina@example.test', matric_number='NUR/P/1',
            department=cls.dept, level=Level.LEVEL_100, admission_session=cls.session,
        )
        cls.student.user.must_change_password = False
        cls.student.user.save(update_fields=['must_change_password'])
        cls.registrar = get_user_model().objects.create_user(username='reg', password='x', role=Role.REGISTRAR)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def payload(self, **overrides):
        data = {
            'account-email': 'amina.new@example.test', 'account-phone_number': '08031234567',
            'personal-date_of_birth': '2004-03-15', 'personal-gender': 'female',
            'personal-marital_status': 'single', 'personal-religion': 'islam',
            'personal-nationality': 'Nigerian', 'personal-state_of_origin': 'Jigawa',
            'personal-lga_of_origin': 'Hadejia', 'personal-blood_group': 'O+', 'personal-genotype': 'AA',
            'personal-home_address': '12 Market Road, Hadejia',
            'guardian-full_name': 'Alhaji Bello Musa', 'guardian-relationship': 'father',
            'guardian-phone_number': '08099998888', 'guardian-email': 'bello@example.test',
            'guardian-occupation': 'Trader', 'guardian-address': '12 Market Road, Hadejia',
        }
        data.update(overrides)
        return data

    def save_profile(self, photo=None, **overrides):
        data = self.payload(**overrides)
        if photo is not None:
            data['account-photo'] = photo
        return self.client_for(self.student.user).post(reverse('students:my_profile'), data, follow=True)

    def photo(self, name='me.png', **kwargs):
        return SimpleUploadedFile(name, _image_bytes(**kwargs), content_type='image/png')

    # --- the page -------------------------------------------------------
    def test_student_sees_the_profile_page_with_all_three_sections(self):
        response = self.client_for(self.student.user).get(reverse('students:my_profile'))
        self.assertContains(response, 'Contact &amp; profile picture')
        self.assertContains(response, 'Personal details')
        self.assertContains(response, 'Parent / guardian details')
        self.assertContains(response, 'Profile completeness')

    def test_only_students_can_open_it(self):
        response = self.client_for(self.registrar).get(reverse('students:my_profile'))
        self.assertNotEqual(response.status_code, 200)

    # --- saving ---------------------------------------------------------
    def test_saves_personal_details_guardian_and_contact_together(self):
        response = self.save_profile(photo=self.photo())
        self.assertContains(response, 'Your profile has been saved')
        student = Student.objects.get(pk=self.student.pk)
        self.assertEqual(student.date_of_birth, date(2004, 3, 15))
        self.assertEqual((student.gender, student.state_of_origin, student.blood_group), ('female', 'Jigawa', 'O+'))
        self.assertEqual(student.home_address, '12 Market Road, Hadejia')
        guardian = student.guardian
        self.assertEqual(
            (guardian.full_name, guardian.relationship, guardian.occupation),
            ('Alhaji Bello Musa', 'father', 'Trader'),
        )
        self.assertEqual((guardian.phone_number, guardian.email), ('08099998888', 'bello@example.test'))
        student.user.refresh_from_db()
        self.assertEqual((student.user.email, student.user.phone_number), ('amina.new@example.test', '08031234567'))

    def test_saving_again_updates_the_same_guardian(self):
        from apps.students.models import Guardian
        self.save_profile()
        self.save_profile(**{'guardian-full_name': 'Hajiya Zainab', 'guardian-relationship': 'mother'})
        self.assertEqual(Guardian.objects.filter(student=self.student).count(), 1)
        self.assertEqual(Guardian.objects.get(student=self.student).full_name, 'Hajiya Zainab')

    def test_nationality_is_only_a_suggestion_until_saved(self):
        self.assertEqual(Student.objects.get(pk=self.student.pk).nationality, '')
        response = self.client_for(self.student.user).get(reverse('students:my_profile'))
        self.assertContains(response, 'value="Nigerian"')

    # --- validation -----------------------------------------------------
    def test_required_fields_and_guardian_are_enforced(self):
        for field in ('personal-date_of_birth', 'personal-gender', 'personal-home_address',
                      'guardian-full_name', 'guardian-relationship', 'guardian-phone_number', 'guardian-address'):
            response = self.save_profile(**{field: ''})
            self.assertNotContains(response, 'Your profile has been saved', msg_prefix=field)
        self.assertIsNone(Student.objects.get(pk=self.student.pk).date_of_birth)

    def test_date_of_birth_must_be_sensible(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        self.assertContains(self.save_profile(**{'personal-date_of_birth': future}), 'cannot be in the future')
        self.assertContains(
            self.save_profile(**{'personal-date_of_birth': '1900-01-01'}), 'Please check the date of birth',
        )

    def test_bad_phone_numbers_rejected(self):
        response = self.save_profile(**{'guardian-phone_number': 'call me'})
        self.assertNotContains(response, 'Your profile has been saved')

    def test_a_failed_save_changes_nothing(self):
        bad = SimpleUploadedFile('fake.png', b'not really an image', content_type='image/png')
        response = self.save_profile(photo=bad)
        self.assertNotContains(response, 'Your profile has been saved')
        student = Student.objects.get(pk=self.student.pk)
        self.assertIsNone(student.date_of_birth)  # the valid personal section was not half-saved
        self.assertFalse(hasattr(student, 'guardian'))

    def test_oversized_and_wrong_type_photos_rejected(self):
        wrong = SimpleUploadedFile('cv.pdf', b'%PDF-1.4', content_type='application/pdf')
        self.assertNotContains(self.save_profile(photo=wrong), 'Your profile has been saved')
        big = SimpleUploadedFile('big.png', b'x' * (3 * 1024 * 1024), content_type='image/png')
        self.assertNotContains(self.save_profile(photo=big), 'Your profile has been saved')

    # --- the picture ----------------------------------------------------
    def test_photo_is_resized_converted_and_stored_under_a_random_name(self):
        from PIL import Image
        self.save_profile(photo=self.photo(name='IMG_001 my face.png', size=(1200, 1500)))
        avatar = User.objects.get(pk=self.student.user.pk).avatar
        self.assertTrue(avatar.name.endswith('.jpg'))
        self.assertNotIn('my face', avatar.name)
        with Image.open(avatar.path) as stored:
            self.assertEqual(stored.format, 'JPEG')
            self.assertLessEqual(max(stored.size), 600)
            self.assertAlmostEqual(stored.size[1] / stored.size[0], 1.25, places=1)  # proportions kept

    def test_landscape_photo_is_cropped_to_passport_proportions_not_stretched(self):
        from PIL import Image
        self.save_profile(photo=self.photo(size=(1600, 1000)))
        with Image.open(User.objects.get(pk=self.student.user.pk).avatar.path) as stored:
            self.assertEqual(stored.size, (480, 600))

    def test_transparent_png_is_flattened_onto_white(self):
        from PIL import Image
        self.save_profile(photo=SimpleUploadedFile(
            'logo.png', _image_bytes(size=(200, 200), mode='RGBA', color=(0, 0, 0, 0)), content_type='image/png',
        ))
        with Image.open(User.objects.get(pk=self.student.user.pk).avatar.path) as stored:
            self.assertGreater(min(stored.getpixel((100, 100))), 240)  # white, not black

    def test_replacing_the_photo_deletes_the_old_file(self):
        import os
        self.save_profile(photo=self.photo())
        first = User.objects.get(pk=self.student.user.pk).avatar.path
        self.save_profile(photo=self.photo(color=(200, 30, 30)))
        second = User.objects.get(pk=self.student.user.pk).avatar.path
        self.assertNotEqual(first, second)
        self.assertFalse(os.path.exists(first))
        self.assertTrue(os.path.exists(second))

    def test_saving_without_a_new_photo_keeps_the_current_one(self):
        self.save_profile(photo=self.photo())
        before = User.objects.get(pk=self.student.user.pk).avatar.name
        self.save_profile()
        self.assertEqual(User.objects.get(pk=self.student.user.pk).avatar.name, before)

    # --- dashboard ------------------------------------------------------
    def test_dashboard_prompts_until_the_profile_is_complete(self):
        client = self.client_for(self.student.user)
        response = client.get(reverse('dashboard:student'))
        self.assertContains(response, 'Complete my profile')
        self.assertContains(response, 'Still needed')
        self.assertContains(response, 'Profile picture')
        self.save_profile(photo=self.photo())
        response = client.get(reverse('dashboard:student'))
        self.assertContains(response, 'Profile 100% complete')
        self.assertNotContains(response, 'Still needed')
        self.assertContains(response, 'View / edit profile')

    def test_sidebar_sends_students_to_their_profile_page(self):
        response = self.client_for(self.student.user).get(reverse('dashboard:student'))
        self.assertContains(response, 'href="%s"' % reverse('students:my_profile'))

    def test_admin_shows_the_guardian_on_the_student_record(self):
        from django.contrib.auth import get_user_model
        self.save_profile()
        admin_user = get_user_model().objects.create_superuser(username='su2', password='x', email='su2@example.test')
        response = self.client_for(admin_user).get(reverse('admin:students_student_change', args=[self.student.pk]))
        self.assertContains(response, 'Alhaji Bello Musa')


@override_settings(MEDIA_ROOT=_MEDIA)
class RegistrationFormPhotoTests(TestCase):
    """The Course Registration Form (registration slip) carries the logo and the profile picture."""

    @classmethod
    def setUpTestData(cls):
        from apps.academics.models import LevelSemesterState, Semester
        from apps.core.constants import SemesterName

        cls.session = AcademicSession.objects.create(name='2096/2097')
        cls.semester = Semester.objects.create(session=cls.session, name=SemesterName.FIRST)
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=cls.semester)
        cls.dept = Department.objects.create(name='Nursing Dept', code='NUR')
        cls.student, _ = create_student(
            first_name='Amina', last_name='Bello', email='amina@example.test', matric_number='NUR/C/1',
            department=cls.dept, level=Level.LEVEL_100, admission_session=cls.session,
        )
        cls.student.user.must_change_password = False
        cls.student.user.save(update_fields=['must_change_password'])
        Student.objects.filter(pk=cls.student.pk).update(
            gender='female', date_of_birth=date(2004, 3, 15), state_of_origin='Jigawa',
        )

    def slip(self):
        client = Client()
        client.force_login(self.student.user)
        with mock.patch('apps.courses.views.selectors.is_registration_approved', return_value=True):
            return client.get(reverse('courses:registration_slip'))

    def pdf(self, response):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(response.content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        images = sum(len(page.images) for page in reader.pages)
        return text, images

    def test_form_without_a_photo_shows_an_affix_box_and_still_prints(self):
        response = self.slip()
        self.assertEqual(response.status_code, 200)
        text, images = self.pdf(response)
        self.assertEqual(images, 1)  # the college crest only
        self.assertIn('Affix passport', text)
        self.assertIn('COURSE REGISTRATION FORM', text)

    def test_form_carries_the_profile_picture_and_bio_data(self):
        from apps.students.services import update_profile_photo
        update_profile_photo(self.student.user, SimpleUploadedFile('p.png', _image_bytes(), content_type='image/png'))
        text, images = self.pdf(self.slip())
        self.assertEqual(images, 2)  # crest + the student's picture
        self.assertNotIn('Affix passport', text)
        for expected in ('AMINA BELLO', 'NUR/C/1', '15 March 2004', 'Female', 'Jigawa'):
            self.assertIn(expected, text)

    def test_a_missing_picture_file_does_not_break_the_form(self):
        import os
        from apps.students.services import update_profile_photo
        update_profile_photo(self.student.user, SimpleUploadedFile('p.png', _image_bytes(), content_type='image/png'))
        os.remove(self.student.user.avatar.path)
        response = self.slip()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Affix passport', self.pdf(response)[0])


class ProfileCompletenessTests(TestCase):
    def test_new_student_is_incomplete_and_lists_what_is_missing(self):
        from apps.students.selectors import get_profile_completeness
        session = AcademicSession.objects.create(name='2096/2097')
        dept = Department.objects.create(name='D', code='DDD')
        student, _ = create_student(
            first_name='A', last_name='B', email='ab@example.test', matric_number='D/1',
            department=dept, level=Level.LEVEL_100, admission_session=session,
        )
        result = get_profile_completeness(student)
        self.assertFalse(result['complete'])
        self.assertEqual(result['percent'], 0)
        self.assertIn('Profile picture', result['missing'])
        self.assertIn("Guardian's name", result['missing'])
