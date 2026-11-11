from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics import selectors, services
from apps.academics.models import AcademicSession, LevelSemesterState, Semester
from apps.admissions.models import Programme
from apps.core.constants import Level, Role

User = get_user_model()


class LevelSemesterSelectorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='reg', password='x', role=Role.REGISTRAR)
        cls.cert = Programme.objects.create(name='Certificate', short_code='CERT', duration_levels=2)
        cls.dip = Programme.objects.create(name='Diploma', short_code='DIP', duration_levels=3)
        session = AcademicSession.objects.create(
            name='2026/2027', start_date='2026-09-01', end_date='2027-07-31',
        )
        cls.sem1 = Semester.objects.create(session=session, name='first')
        cls.sem2 = Semester.objects.create(session=session, name='second')

    def setUp(self):
        self.client.force_login(self.user)

    def test_levels_endpoint_scoped_to_programme(self):
        data = self.client.get(reverse('academics:level_state_levels'), {'programme': self.cert.pk}).json()
        self.assertEqual([l['value'] for l in data['levels']], [100, 200])
        data = self.client.get(reverse('academics:level_state_levels'), {'programme': self.dip.pk}).json()
        self.assertEqual([l['value'] for l in data['levels']], [100, 200, 300])

    def test_levels_endpoint_bad_or_missing_programme_is_empty(self):
        url = reverse('academics:level_state_levels')
        self.assertEqual(self.client.get(url).json(), {'levels': []})
        self.assertEqual(self.client.get(url, {'programme': 'nope'}).json(), {'levels': []})

    def test_semesters_endpoint_valid_pair(self):
        data = self.client.get(
            reverse('academics:level_state_semesters'), {'programme': self.cert.pk, 'level': 200},
        ).json()
        self.assertEqual({s['value'] for s in data['semesters']}, {str(self.sem1.pk), str(self.sem2.pk)})

    def test_semesters_endpoint_rejects_level_outside_programme(self):
        data = self.client.get(
            reverse('academics:level_state_semesters'), {'programme': self.cert.pk, 'level': 300},
        ).json()
        self.assertEqual(data, {'semesters': []})

    def test_post_valid_selection_sets_level_state(self):
        self.client.post(reverse('academics:level_states'), {
            'programme': self.dip.pk, 'level': 300, 'semester': self.sem2.pk,
        })
        self.assertEqual(LevelSemesterState.objects.get(level=Level.LEVEL_300).semester, self.sem2)

    def test_post_invalid_combination_rejected(self):
        self.client.post(reverse('academics:level_states'), {
            'programme': self.cert.pk, 'level': 300, 'semester': self.sem1.pk,
        })
        self.assertFalse(LevelSemesterState.objects.exists())

    def test_existing_per_row_form_still_works(self):
        url = reverse('academics:level_states')
        self.client.post(url, {'level': 100, 'semester': self.sem1.pk})
        self.assertEqual(LevelSemesterState.objects.get(level=100).semester, self.sem1)
        self.client.post(url, {'level': 100, 'semester': ''})
        self.assertFalse(LevelSemesterState.objects.filter(level=100).exists())

    def test_page_renders_programmes(self):
        response = self.client.get(reverse('academics:level_states'))
        self.assertContains(response, 'Certificate')
        self.assertContains(response, 'sel-programme')


class ProgrammeSpecificStateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='reg2', password='x', role=Role.REGISTRAR)
        cls.admin_user = User.objects.create_superuser(username='root', password='x', email='r@x.com')
        cls.cert = Programme.objects.create(name='Certificate', short_code='CERT', duration_levels=2)
        cls.dip = Programme.objects.create(name='Diploma', short_code='DIP', duration_levels=3)
        session = AcademicSession.objects.create(name='2026/2027', start_date='2026-09-01', end_date='2027-07-31')
        cls.sem1 = Semester.objects.create(session=session, name='first')
        cls.sem2 = Semester.objects.create(session=session, name='second')

    def test_default_row_applies_to_every_programme(self):
        services.set_level_semester(100, self.sem1)
        self.assertEqual(selectors.get_semester_for_level(100), self.sem1)
        self.assertEqual(selectors.get_semester_for_level(100, self.cert.pk), self.sem1)

    def test_programme_override_only_affects_that_programme(self):
        services.set_level_semester(100, self.sem1)
        services.set_level_semester(100, self.sem2, programme=self.cert)
        self.assertEqual(selectors.get_semester_for_level(100, self.cert), self.sem2)
        self.assertEqual(selectors.get_semester_for_level(100, self.dip), self.sem1)
        self.assertEqual(selectors.get_semester_for_level(100), self.sem1)

    def test_no_default_and_no_override_is_none(self):
        services.set_level_semester(100, self.sem2, programme=self.cert)
        self.assertIsNone(selectors.get_semester_for_level(100, self.dip))

    def test_selector_post_saves_per_programme_and_use_default_removes(self):
        self.client.force_login(self.user)
        url = reverse('academics:level_states')
        self.client.post(url, {'programme': self.cert.pk, 'level': 200, 'semester': self.sem2.pk})
        state = LevelSemesterState.objects.get(level=200, programme=self.cert)
        self.assertFalse(LevelSemesterState.objects.filter(level=200, programme=self.dip).exists())
        self.client.post(url, {'remove_programme_state': state.pk})
        self.assertFalse(LevelSemesterState.objects.exists())

    def test_exact_duplicate_default_rows_blocked_but_other_semesters_allowed(self):
        from django.db import IntegrityError, transaction

        LevelSemesterState.objects.create(level=100, semester=self.sem1)
        LevelSemesterState.objects.create(level=100, semester=self.sem2)  # different semester: allowed
        with self.assertRaises(IntegrityError), transaction.atomic():
            LevelSemesterState.objects.create(level=100, semester=self.sem1)  # exact duplicate

    def test_admin_filters_cascade(self):
        self.client.force_login(self.admin_user)
        services.set_level_semester(100, self.sem1, programme=self.cert)
        services.set_level_semester(100, self.sem1, programme=self.dip)
        url = reverse('admin:academics_levelsemesterstate_changelist')
        response = self.client.get(url)
        self.assertContains(response, '1. Program')
        self.assertNotContains(response, '2. Level')
        response = self.client.get(url, {'programme': self.cert.pk})
        self.assertContains(response, '2. Level')
        self.assertNotContains(response, '3. Semester - Session')
        self.assertEqual(response.context['cl'].result_count, 1)
        response = self.client.get(url, {'programme': self.cert.pk, 'level_sel': 100})
        self.assertContains(response, '3. Semester - Session')
        response = self.client.get(url, {'programme': self.cert.pk, 'level_sel': 100, 'semester_sel': self.sem1.pk})
        self.assertEqual(response.context['cl'].result_count, 1)
        self.assertEqual(response.status_code, 200)

    def test_admin_form_rejects_invalid_combination(self):
        from apps.academics.admin import LevelSemesterStateAdminForm

        form = LevelSemesterStateAdminForm(
            {'programme': self.cert.pk, 'level': 300, 'semester': self.sem1.pk},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('level', form.errors)


class LevelStateUniquenessTests(TestCase):
    """Programme + Level + Semester (which carries its session) is the
    uniqueness rule - not Programme + Level."""

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(username='root2', password='x', email='r2@x.com')
        cls.nd_ch = Programme.objects.create(name='ND Community Health', short_code='NDCH', duration_levels=3)
        cls.nd_nur = Programme.objects.create(name='ND Nursing', short_code='NDN', duration_levels=3)
        s25 = AcademicSession.objects.create(name='2025/2026', start_date='2025-09-01', end_date='2026-07-31')
        s26 = AcademicSession.objects.create(name='2026/2027', start_date='2026-09-01', end_date='2027-07-31')
        cls.first_25 = Semester.objects.create(session=s25, name='first')
        cls.second_25 = Semester.objects.create(session=s25, name='second')
        cls.first_26 = Semester.objects.create(session=s26, name='first')

    def add(self, programme, level, semester):
        state = LevelSemesterState(programme=programme, level=level, semester=semester)
        state.full_clean()  # model validation incl. constraints - what the admin form runs
        state.save()
        return state

    def test_same_programme_and_level_across_semesters_and_sessions_allowed(self):
        self.add(self.nd_ch, 100, self.first_25)
        self.add(self.nd_ch, 100, self.second_25)
        self.add(self.nd_ch, 100, self.first_26)
        self.add(self.nd_ch, 200, self.first_26)
        self.add(self.nd_nur, 100, self.first_26)
        self.assertEqual(LevelSemesterState.objects.filter(programme=self.nd_ch, level=100).count(), 3)

    def test_exact_duplicate_rejected_with_clear_message(self):
        from django.core.exceptions import ValidationError

        self.add(self.nd_ch, 100, self.first_26)
        with self.assertRaises(ValidationError) as ctx:
            self.add(self.nd_ch, 100, self.first_26)
        self.assertIn('already exists', ' '.join(ctx.exception.messages))
        self.assertEqual(LevelSemesterState.objects.count(), 1)

    def test_same_semester_for_another_programme_allowed(self):
        self.add(self.nd_ch, 100, self.first_26)
        self.add(self.nd_nur, 100, self.first_26)
        self.assertEqual(LevelSemesterState.objects.count(), 2)

    def test_default_rows_follow_the_same_rule(self):
        from django.core.exceptions import ValidationError

        self.add(None, 100, self.first_25)
        self.add(None, 100, self.first_26)
        with self.assertRaises(ValidationError):
            self.add(None, 100, self.first_26)

    def test_admin_add_form_allows_new_semester_and_rejects_duplicate(self):
        self.client.force_login(self.admin_user)
        url = reverse('admin:academics_levelsemesterstate_add')
        data = {'programme': self.nd_ch.pk, 'level': 100, 'semester': self.first_25.pk}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        data['semester'] = self.first_26.pk
        self.assertEqual(self.client.post(url, data).status_code, 302)
        response = self.client.post(url, data)  # exact duplicate
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')
        self.assertEqual(LevelSemesterState.objects.filter(programme=self.nd_ch, level=100).count(), 2)

    def test_registrar_page_rejects_duplicate_and_accepts_new_semester(self):
        registrar = User.objects.create_user(username='reg3', password='x', role=Role.REGISTRAR)
        self.client.force_login(registrar)
        url = reverse('academics:level_states')
        data = {'programme': self.nd_ch.pk, 'level': 100, 'semester': self.first_25.pk}
        self.client.post(url, data)
        data['semester'] = self.second_25.pk
        self.client.post(url, data)
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, 'already exists')
        self.assertEqual(LevelSemesterState.objects.filter(programme=self.nd_ch, level=100).count(), 2)

    def test_current_semester_is_the_latest_and_history_does_not_leak(self):
        self.add(self.nd_ch, 100, self.first_26)
        self.add(self.nd_ch, 100, self.first_25)  # added later, but older: history
        self.add(self.nd_ch, 100, self.second_25)
        self.assertEqual(selectors.get_semester_for_level(100, self.nd_ch), self.first_26)
        current = list(selectors.get_level_semester_states())
        self.assertEqual([s.semester for s in current], [self.first_26])
        self.assertEqual(set(selectors.get_current_semesters()), {self.first_26})
        self.assertEqual(LevelSemesterState.objects.count(), 3)  # nothing lost

    def test_clearing_removes_only_the_current_semester(self):
        self.add(None, 100, self.first_25)
        self.add(None, 100, self.first_26)
        removed = services.clear_level_semester(100)
        self.assertEqual(removed.semester, self.first_26)
        self.assertEqual(selectors.get_semester_for_level(100), self.first_25)
        self.assertEqual(LevelSemesterState.objects.count(), 1)

    def test_existing_single_rows_behave_as_before(self):
        # rows as they existed before this change: one per level
        LevelSemesterState.objects.create(level=100, semester=self.first_25)
        LevelSemesterState.objects.create(level=200, semester=self.first_26)
        self.assertEqual(selectors.get_semester_for_level(100), self.first_25)
        self.assertEqual(selectors.get_semester_for_level(200, self.nd_ch), self.first_26)
        self.assertEqual(LevelSemesterState.objects.count(), 2)
