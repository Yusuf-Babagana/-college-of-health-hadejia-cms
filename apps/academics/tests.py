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


class ProgrammeSessionSemesterFormTests(TestCase):
    """Semester form: PROGRAMME -> ACADEMIC SESSION -> SEMESTER."""

    @classmethod
    def setUpTestData(cls):
        from apps.academics.forms import SemesterForm
        cls.form_class = SemesterForm
        cls.nursing = Programme.objects.create(name='Nursing', short_code='NUR', duration_levels=4)
        cls.midwifery = Programme.objects.create(name='Midwifery', short_code='MID', duration_levels=4)
        cls.s_nursing = AcademicSession.objects.create(name='2026/2027')
        cls.s_nursing.programmes.add(cls.nursing)
        cls.s_midwifery = AcademicSession.objects.create(name='2027/2028')
        cls.s_midwifery.programmes.add(cls.midwifery)
        cls.s_all = AcademicSession.objects.create(name='2025/2026')  # no programmes: applies to all
        cls.registrar = get_user_model().objects.create_user(username='reg', password='x', role=Role.REGISTRAR)

    def data(self, **overrides):
        values = {'programme': self.nursing.pk, 'session': self.s_nursing.pk, 'name': 'first'}
        values.update(overrides)
        return values

    def test_1_programme_dropdown_lists_programmes_and_is_required(self):
        form = self.form_class()
        listed = {p.pk for p in form.fields['programme'].queryset}
        self.assertLessEqual({self.nursing.pk, self.midwifery.pk}, listed)  # (migrations also seed programmes)
        self.assertTrue(form.fields['programme'].required)
        self.assertEqual(list(form.fields)[:3], ['programme', 'session', 'name'])

    def test_2_selecting_a_programme_loads_its_sessions(self):
        client = self.client
        client.force_login(self.registrar)
        response = client.get(reverse('academics:semester_session_options'), {'programme': self.nursing.pk})
        labels = {s['label'] for s in response.json()['sessions']}
        self.assertEqual(labels, {'2026/2027', '2025/2026'})

    def test_3_other_programmes_sessions_are_excluded(self):
        self.client.force_login(self.registrar)
        response = self.client.get(reverse('academics:semester_session_options'), {'programme': self.nursing.pk})
        self.assertNotIn('2027/2028', {s['label'] for s in response.json()['sessions']})

    def test_session_options_empty_without_or_with_bad_programme(self):
        self.client.force_login(self.registrar)
        url = reverse('academics:semester_session_options')
        self.assertEqual(self.client.get(url).json()['sessions'], [])
        self.assertEqual(self.client.get(url, {'programme': 'not-a-uuid'}).json()['sessions'], [])

    def test_session_is_disabled_until_a_programme_is_chosen(self):
        self.assertTrue(self.form_class().fields['session'].widget.attrs.get('disabled'))
        self.assertEqual(self.form_class().fields['session'].queryset.count(), 0)
        bound = self.form_class(data=self.data())
        self.assertFalse(bound.fields['session'].widget.attrs.get('disabled'))

    def test_4_changing_programme_resets_session_server_side(self):
        # Browser reset is JS; the server guarantee is that the old session
        # no longer validates once the programme changes.
        form = self.form_class(data=self.data(programme=self.midwifery.pk))
        self.assertFalse(form.is_valid())
        self.assertIn('session', form.errors)

    def test_5_cannot_create_without_programme_or_session(self):
        for missing in ('programme', 'session'):
            data = self.data()
            data.pop(missing)
            form = self.form_class(data=data)
            self.assertFalse(form.is_valid())
            self.assertIn(missing, form.errors)

    def test_6_invalid_programme_session_combination_is_rejected(self):
        form = self.form_class(data=self.data(session=self.s_midwifery.pk))
        self.assertFalse(form.is_valid())
        self.assertIn('session', form.errors)
        self.assertFalse(Semester.objects.exists())

    def test_model_clean_rejects_invalid_combination_even_outside_the_form(self):
        from django.core.exceptions import ValidationError
        semester = Semester(programme=self.nursing, session=self.s_midwifery, name='first')
        with self.assertRaises(ValidationError):
            semester.full_clean()

    def test_valid_semester_saves_and_is_retrieved_with_its_programme(self):
        form = self.form_class(data=self.data())
        self.assertTrue(form.is_valid(), form.errors)
        semester = form.save()
        semester.refresh_from_db()
        self.assertEqual((semester.programme, semester.session), (self.nursing, self.s_nursing))
        edit = self.form_class(instance=semester)
        self.assertEqual(edit['programme'].value(), self.nursing.pk)
        self.assertIn(self.s_nursing, edit.fields['session'].queryset)
        self.assertNotIn(self.s_midwifery, edit.fields['session'].queryset)

    def test_session_with_no_programmes_applies_to_every_programme(self):
        for programme in (self.nursing, self.midwifery):
            form = self.form_class(data=self.data(programme=programme.pk, session=self.s_all.pk, name='second'))
            self.assertTrue(form.is_valid(), form.errors)

    def test_create_view_end_to_end(self):
        self.client.force_login(self.registrar)
        response = self.client.get(reverse('academics:semester_create'))
        self.assertContains(response, 'programme-session-select.js')
        self.client.post(reverse('academics:semester_create'), self.data(), follow=True)
        self.assertEqual(Semester.objects.get().programme, self.nursing)

    def test_7_existing_semesters_and_level_states_are_untouched(self):
        legacy = Semester.objects.create(session=self.s_all, name='first')  # no programme, as before
        state = LevelSemesterState.objects.create(level=100, semester=legacy)
        self.assertIsNone(legacy.programme)
        legacy.full_clean()  # still valid without a programme
        self.assertEqual(selectors.get_semester_for_level(100), legacy)
        self.assertEqual(state.semester, legacy)
        self.assertTrue(list(selectors.get_semester_list()))  # list query still works

    def test_django_admin_uses_the_same_form(self):
        from django.contrib import admin as dj_admin
        model_admin = dj_admin.site._registry[Semester]
        self.assertIn('programme', model_admin.form.base_fields)
        self.assertEqual(list(model_admin.form.base_fields)[:2], ['programme', 'session'])
        superuser = get_user_model().objects.create_superuser(username='su', password='x', email='su@example.test')
        self.client.force_login(superuser)
        self.assertEqual(self.client.get(reverse('admin:academics_semester_add')).status_code, 200)
        response = self.client.post(reverse('admin:academics_semester_add'), self.data(session=self.s_midwifery.pk))
        self.assertEqual(response.status_code, 200)  # re-rendered with the error
        self.assertFalse(Semester.objects.exists())


class SemesterUniquePerProgrammeTests(TestCase):
    """Uniqueness is Programme + Academic Session + Semester name."""

    @classmethod
    def setUpTestData(cls):
        from apps.academics.forms import SemesterForm
        cls.form_class = SemesterForm
        cls.certificate = Programme.objects.create(name='Certificate in Community Health', short_code='CCH2', duration_levels=2)
        cls.nursing = Programme.objects.create(name='ND Nursing', short_code='NDN', duration_levels=3)
        cls.chd = Programme.objects.create(name='ND Community Health', short_code='NDC', duration_levels=3)
        cls.session = AcademicSession.objects.create(name='2026/2027')  # no programmes listed: applies to all

    def submit(self, programme, name):
        form = self.form_class(data={'programme': programme.pk, 'session': self.session.pk, 'name': name})
        return form, form.is_valid() and form.save()

    def test_1_same_name_same_session_different_programmes_allowed(self):
        for programme in (self.certificate, self.nursing, self.chd):
            form, saved = self.submit(programme, 'first')
            self.assertTrue(saved, form.errors)
        self.assertEqual(Semester.objects.filter(session=self.session, name='first').count(), 3)

    def test_2_different_names_same_session_same_programme_allowed(self):
        self.assertTrue(self.submit(self.certificate, 'first')[1])
        self.assertTrue(self.submit(self.certificate, 'second')[1])

    def test_3_same_programme_session_and_name_is_rejected_with_a_clear_message(self):
        self.assertTrue(self.submit(self.certificate, 'first')[1])
        form, saved = self.submit(self.certificate, 'first')
        self.assertFalse(saved)
        self.assertIn('already exists for this Programme, Academic Session and Semester name', str(form.errors))
        self.assertEqual(Semester.objects.filter(programme=self.certificate).count(), 1)

    def test_database_constraint_also_blocks_the_duplicate(self):
        from django.db import IntegrityError, transaction
        Semester.objects.create(programme=self.certificate, session=self.session, name='first')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Semester.objects.create(programme=self.certificate, session=self.session, name='first')

    def test_legacy_semesters_without_a_programme_stay_unique_per_session_and_name(self):
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError, transaction
        Semester.objects.create(session=self.session, name='first')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Semester.objects.create(session=self.session, name='first')
        with self.assertRaises(ValidationError):
            Semester(session=self.session, name='first').validate_constraints()
        # ...but a programme-specific one alongside it is fine
        self.assertTrue(self.submit(self.certificate, 'first')[1])

    def test_4_existing_semesters_remain_accessible(self):
        legacy = Semester.objects.create(session=self.session, name='second')
        LevelSemesterState.objects.create(level=100, semester=legacy)
        self.assertEqual(selectors.get_semester_for_level(100), legacy)
        self.assertEqual(str(legacy), 'Second Semester - 2026/2027')  # label unchanged for legacy rows
        self.assertIn(legacy, selectors.get_semester_list())

    def test_label_distinguishes_same_named_semesters_of_different_programmes(self):
        a = Semester.objects.create(programme=self.certificate, session=self.session, name='first')
        b = Semester.objects.create(programme=self.nursing, session=self.session, name='first')
        self.assertEqual(str(a), 'First Semester - 2026/2027 [CCH2]')
        self.assertNotEqual(str(a), str(b))

    def test_5_level_states_only_offer_and_accept_the_programmes_own_semesters(self):
        from apps.academics.forms import LevelSemesterSelectionForm
        mine = Semester.objects.create(programme=self.certificate, session=self.session, name='first')
        theirs = Semester.objects.create(programme=self.nursing, session=self.session, name='first')
        legacy = Semester.objects.create(session=self.session, name='second')
        offered = set(selectors.get_semesters_for_selection(self.certificate))
        self.assertEqual(offered, {mine, legacy})
        form = LevelSemesterSelectionForm(data={'programme': self.certificate.pk, 'level': 100, 'semester': theirs.pk})
        self.assertFalse(form.is_valid())
        self.assertIn('semester', form.errors)
        ok = LevelSemesterSelectionForm(data={'programme': self.certificate.pk, 'level': 100, 'semester': mine.pk})
        self.assertTrue(ok.is_valid(), ok.errors)
