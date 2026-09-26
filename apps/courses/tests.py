"""
Automated tests for course/programme eligibility. Uses TestCase, so
every test runs inside a transaction that Django rolls back afterwards -
nothing here ever touches the real development database, and none of
this data survives past the test run.
"""
from datetime import timedelta
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.admissions.models import Programme
from apps.core.constants import Level, Role, SemesterName
from apps.courses import selectors, services
from apps.courses.models import Course, CourseOffering, CourseRegistration
from apps.courses.selectors import get_course_offerings_for_programme, get_department_course_tree
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


class GetDepartmentCourseTreeTests(TestCase):
    """Regression tests for the Programme -> Level -> Semester tree on the
    HOD dashboard / course-allocation screen. The live bug: a course
    assigned to a Programme whose own ``department`` was never set (the
    field is nullable and defaults to NULL - true for every existing
    Programme) vanished from the tree entirely, because the tree only
    built sections for ``Programme.objects.filter(department=dept)`` and
    such a course is also excluded from the "No Programme" bucket.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='Tree Department', code='TRD')
        cls.programme_scoped = Programme.objects.create(
            name='Scoped Programme', short_code='TRSCOPED', department=cls.dept, duration_levels=4,
        )
        cls.programme_unscoped = Programme.objects.create(
            name='Unscoped Programme', short_code='TRUNSCOPED', department=None, duration_levels=4,
        )

    def _course(self, code, programme, level=Level.LEVEL_100):
        return Course.objects.create(
            code=code, title=code, credit_units=2, level=level,
            department=self.dept, semester_name=SemesterName.FIRST, programme=programme,
        )

    def _courses_in_tree(self, tree):
        found = []
        for entry in tree:
            for level in entry['levels']:
                for semester in level['semesters']:
                    found.extend(semester['courses'])
        return found

    def test_course_on_programme_with_no_department_still_appears(self):
        course = self._course('TRD101', self.programme_unscoped)

        tree = get_department_course_tree(self.dept)

        self.assertIn(course, self._courses_in_tree(tree))
        section = next(e for e in tree if e['programme'] == self.programme_unscoped)
        self.assertIn(course, self._courses_in_tree([section]))

    def test_course_on_scoped_programme_appears_under_that_programme(self):
        course = self._course('TRD102', self.programme_scoped)

        tree = get_department_course_tree(self.dept)

        section = next(e for e in tree if e['programme'] == self.programme_scoped)
        self.assertIn(course, self._courses_in_tree([section]))

    def test_empty_scoped_programme_still_gets_a_skeleton_section(self):
        tree = get_department_course_tree(self.dept)

        self.assertTrue(any(e['programme'] == self.programme_scoped for e in tree))

    def test_course_mislevelled_past_programme_duration_is_not_dropped(self):
        short_programme = Programme.objects.create(
            name='Short Tree Programme', short_code='TRSHORT', department=self.dept, duration_levels=2,
        )
        # Force a Level 300 course onto a 2-level programme, bypassing
        # Course.clean() the way a bulk update / raw admin save can.
        course = self._course('TRD301', None, level=Level.LEVEL_300)
        Course.objects.filter(pk=course.pk).update(programme=short_programme)
        course.refresh_from_db()

        tree = get_department_course_tree(self.dept)

        section = next(e for e in tree if e['programme'] == short_programme)
        self.assertIn(course, self._courses_in_tree([section]))


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


class RegistrationApprovalTests(TestCase):
    """FR-HOD-07: HOD approval gate on top of course registration -
    self-service add/drop is free while pending, locks once the HOD
    approves, and the HOD dashboard (hod_register_course /
    hod_cancel_registration) is the only route for changes after that.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.students.services import create_student

        cls.session = cls._make_session()
        cls.semester = cls._make_semester(cls.session, registration_open=True)
        cls.dept = Department.objects.create(name='Approval Department', code='APR')

        cls.student, _ = create_student(
            first_name='Amina', last_name='Yusuf', email='amina.yusuf@example.test',
            matric_number='APR/2099/0001', department=cls.dept, level=Level.LEVEL_100,
            admission_session=cls.session,
        )
        cls.course = Course.objects.create(
            code='APR101', title='Approval Course', credit_units=3, level=Level.LEVEL_100,
            department=cls.dept, semester_name=SemesterName.FIRST,
        )
        cls.offering = CourseOffering.objects.create(course=cls.course, semester=cls.semester, capacity=50)

        cls.other_course = Course.objects.create(
            code='APR102', title='Second Approval Course', credit_units=2, level=Level.LEVEL_100,
            department=cls.dept, semester_name=SemesterName.FIRST,
        )
        cls.other_offering = CourseOffering.objects.create(
            course=cls.other_course, semester=cls.semester, capacity=50,
        )

    @staticmethod
    def _make_session():
        from apps.academics.models import AcademicSession
        return AcademicSession.objects.create(name='2099/2100')

    @staticmethod
    def _make_semester(session, *, registration_open):
        from apps.academics.models import Semester

        now = timezone.now()
        return Semester.objects.create(
            session=session, name=SemesterName.FIRST,
            registration_start=now - timedelta(days=1) if registration_open else now + timedelta(days=1),
            registration_end=now + timedelta(days=30),
        )

    def _make_hod(self):
        from apps.accounts.models import User

        return User.objects.create_user(
            username='approval.hod', password='x', role=Role.HOD,
        )

    def test_registration_starts_pending_and_unapproved(self):
        services.register_course(student=self.student, course_offering=self.offering)

        self.assertFalse(selectors.is_registration_approved(self.student, self.semester))

    def test_student_can_drop_and_re_add_before_approval(self):
        services.register_course(student=self.student, course_offering=self.offering)

        services.drop_course(student=self.student, course_offering=self.offering)
        registration = CourseRegistration.objects.get(student=self.student, course_offering=self.offering)
        self.assertEqual(registration.status, CourseRegistration.Status.DROPPED)

        services.register_course(student=self.student, course_offering=self.offering)
        registration.refresh_from_db()
        self.assertEqual(registration.status, CourseRegistration.Status.REGISTERED)

    def test_approve_registration_requires_an_active_registration(self):
        with self.assertRaises(ValidationError):
            services.approve_registration(student=self.student, semester=self.semester, reviewer=self._make_hod())

    def test_approve_registration_twice_is_rejected(self):
        services.register_course(student=self.student, course_offering=self.offering)
        hod = self._make_hod()
        services.approve_registration(student=self.student, semester=self.semester, reviewer=hod)

        with self.assertRaises(ValidationError):
            services.approve_registration(student=self.student, semester=self.semester, reviewer=hod)

    def test_approved_registration_blocks_self_service_drop(self):
        services.register_course(student=self.student, course_offering=self.offering)
        services.approve_registration(student=self.student, semester=self.semester, reviewer=self._make_hod())

        with self.assertRaises(ValidationError):
            services.drop_course(student=self.student, course_offering=self.offering)

        registration = CourseRegistration.objects.get(student=self.student, course_offering=self.offering)
        self.assertEqual(registration.status, CourseRegistration.Status.REGISTERED)

    def test_approved_registration_blocks_self_service_add(self):
        services.register_course(student=self.student, course_offering=self.offering)
        services.approve_registration(student=self.student, semester=self.semester, reviewer=self._make_hod())

        with self.assertRaises(ValidationError):
            services.register_course(student=self.student, course_offering=self.other_offering)

    def test_hod_register_course_bypasses_the_approval_lock(self):
        services.register_course(student=self.student, course_offering=self.offering)
        services.approve_registration(student=self.student, semester=self.semester, reviewer=self._make_hod())

        services.hod_register_course(student=self.student, course_offering=self.other_offering)

        self.assertTrue(
            CourseRegistration.objects.filter(
                student=self.student, course_offering=self.other_offering,
                status=CourseRegistration.Status.REGISTERED,
            ).exists()
        )

    def test_hod_cancel_registration_bypasses_the_approval_lock(self):
        services.register_course(student=self.student, course_offering=self.offering)
        services.approve_registration(student=self.student, semester=self.semester, reviewer=self._make_hod())

        registration = CourseRegistration.objects.get(student=self.student, course_offering=self.offering)
        services.hod_cancel_registration(registration)

        registration.refresh_from_db()
        self.assertEqual(registration.status, CourseRegistration.Status.DROPPED)

    def test_unapprove_reopens_self_service_editing(self):
        services.register_course(student=self.student, course_offering=self.offering)
        hod = self._make_hod()
        services.approve_registration(student=self.student, semester=self.semester, reviewer=hod)

        services.unapprove_registration(student=self.student, semester=self.semester, reviewer=hod)

        self.assertFalse(selectors.is_registration_approved(self.student, self.semester))
        services.drop_course(student=self.student, course_offering=self.offering)
        registration = CourseRegistration.objects.get(student=self.student, course_offering=self.offering)
        self.assertEqual(registration.status, CourseRegistration.Status.DROPPED)

    def test_registration_approval_queue_groups_by_student_and_semester(self):
        services.register_course(student=self.student, course_offering=self.offering)
        services.register_course(student=self.student, course_offering=self.other_offering)

        rows = selectors.get_registration_approval_queue(self.dept)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['student'], self.student)
        self.assertEqual(row['semester'], self.semester)
        self.assertEqual(len(row['registrations']), 2)
        self.assertEqual(row['total_units'], 5)
        self.assertFalse(row['is_approved'])


class RegistrationApprovalViewTests(TestCase):
    """End-to-end walk through the URLs/templates for FR-HOD-07: a
    student registers, is blocked from printing/dropping/adding once the
    HOD approves, and the HOD dashboard becomes the only route for
    further changes.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.academics.models import AcademicSession, LevelSemesterState, Semester
        from apps.accounts.models import User
        from apps.core.constants import Level
        from apps.departments.services import assign_hod
        from apps.lecturers.services import create_lecturer_profile
        from apps.students.services import create_student

        cls.session = AcademicSession.objects.create(name='2098/2099')
        now = timezone.now()
        cls.semester = Semester.objects.create(
            session=cls.session, name=SemesterName.FIRST,
            registration_start=now - timedelta(days=1), registration_end=now + timedelta(days=30),
        )
        # Registration/"My Schedule"/the slip all resolve a student's
        # current semester via LevelSemesterState, not this Semester row
        # directly - see per-level-semester-design.
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=cls.semester)
        cls.dept = Department.objects.create(name='View Test Department', code='VTD')

        cls.student, cls.student_password = create_student(
            first_name='Bala', last_name='Musa', email='bala.musa@example.test',
            matric_number='VTD/2098/0001', department=cls.dept, level=Level.LEVEL_100,
            admission_session=cls.session,
        )
        # create_student forces a password change on first login (by
        # design, for real accounts) - irrelevant to this test and would
        # otherwise redirect every request to the change-password page.
        cls.student.user.must_change_password = False
        cls.student.user.save(update_fields=['must_change_password'])

        cls.hod_user = User.objects.create_user(username='vtd.hod', password='hodpass123', role=Role.HOD)
        lecturer = create_lecturer_profile(
            user=cls.hod_user, department=cls.dept, qualification='', specialization='',
            appointment_date=now.date(),
        )
        assign_hod(cls.dept, lecturer)

        cls.course = Course.objects.create(
            code='VTD101', title='View Test Course', credit_units=3, level=Level.LEVEL_100,
            department=cls.dept, semester_name=SemesterName.FIRST,
        )
        cls.offering = CourseOffering.objects.create(course=cls.course, semester=cls.semester, capacity=50)

        cls.other_course = Course.objects.create(
            code='VTD102', title='Second View Test Course', credit_units=2, level=Level.LEVEL_100,
            department=cls.dept, semester_name=SemesterName.FIRST,
        )
        cls.other_offering = CourseOffering.objects.create(
            course=cls.other_course, semester=cls.semester, capacity=50,
        )

    def test_full_approval_workflow_through_the_views(self):
        student_client = Client()
        self.assertTrue(student_client.login(username=self.student.user.username, password=self.student_password))

        # Student registers - available while pending.
        response = student_client.post(reverse('courses:register_course', args=[self.offering.pk]), follow=True)
        self.assertContains(response, 'Registered for VTD101')

        # Slip is not printable yet.
        response = student_client.get(reverse('courses:registration_slip'), follow=True)
        self.assertContains(response, 'only available once your HOD has approved')

        # My Schedule shows the pending banner and an enabled Drop button.
        response = student_client.get(reverse('courses:my_registrations'))
        self.assertContains(response, 'Awaiting HOD approval')
        self.assertContains(response, 'Drop')

        hod_client = Client()
        self.assertTrue(hod_client.login(username='vtd.hod', password='hodpass123'))

        # HOD sees the pending queue and approves it.
        response = hod_client.get(reverse('courses:registration_approvals'))
        self.assertContains(response, self.student.matric_number)
        self.assertContains(response, 'Pending')

        response = hod_client.post(
            reverse('courses:approve_registration', args=[self.student.pk, self.semester.pk]), follow=True,
        )
        self.assertContains(response, 'Approved')

        # Student can no longer drop, and the slip is now printable.
        response = student_client.post(
            reverse('courses:drop_course', args=[self.offering.pk]), follow=True,
        )
        self.assertContains(response, 'contact your HOD to drop a course now')

        response = student_client.get(reverse('courses:registration_slip'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

        response = student_client.get(reverse('courses:my_registrations'))
        self.assertContains(response, "HOD has approved this semester's registration")
        self.assertContains(response, 'Print Registration Slip')
        self.assertNotContains(response, 'Register More')
        self.assertContains(response, 'Contact HOD')

        # Adding more courses now has to go through the HOD dashboard.
        response = student_client.post(
            reverse('courses:register_course', args=[self.other_offering.pk]), follow=True,
        )
        self.assertContains(response, 'contact your HOD to add a course now')

        manage_url = reverse('courses:manage_student_registration', args=[self.student.pk, self.semester.pk])
        response = hod_client.get(manage_url)
        self.assertContains(response, 'VTD102')

        response = hod_client.post(
            reverse('courses:hod_add_course', args=[self.student.pk]),
            {'course_offering': str(self.other_offering.pk)},
            follow=True,
        )
        self.assertContains(response, f'Registered {self.student.matric_number} for VTD102')

        self.assertTrue(
            CourseRegistration.objects.filter(
                student=self.student, course_offering=self.other_offering,
                status=CourseRegistration.Status.REGISTERED,
            ).exists()
        )


class CrossDepartmentLecturerAssignmentTests(TestCase):
    """FR-LEC-01: a lecturer's Lecturer.department is just their one home
    profile/login - the same lecturer (one User account) can still be
    assigned to teach a course offering in another department, and that
    other department's HOD should be able to pick them.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.academics.models import AcademicSession, LevelSemesterState, Semester
        from apps.accounts.models import User
        from apps.departments.services import assign_hod
        from apps.lecturers.services import create_lecturer_profile

        cls.session = AcademicSession.objects.create(name='2097/2098')
        now = timezone.now()
        cls.semester = Semester.objects.create(
            session=cls.session, name=SemesterName.FIRST,
            registration_start=now - timedelta(days=1), registration_end=now + timedelta(days=30),
        )
        LevelSemesterState.objects.create(level=Level.LEVEL_100, semester=cls.semester)

        cls.home_dept = Department.objects.create(name='Home Department', code='HOM')
        cls.other_dept = Department.objects.create(name='Other Department', code='OTR')

        cls.hod_user = User.objects.create_user(username='otr.hod', password='hodpass123', role=Role.HOD)
        hod_lecturer = create_lecturer_profile(
            user=cls.hod_user, department=cls.other_dept, qualification='', specialization='',
            appointment_date=now.date(),
        )
        assign_hod(cls.other_dept, hod_lecturer)

        cls.visiting_user = User.objects.create_user(username='home.lecturer', password='lecpass123', role=Role.LECTURER)
        cls.visiting_lecturer = create_lecturer_profile(
            user=cls.visiting_user, department=cls.home_dept, qualification='PhD', specialization='',
            appointment_date=now.date(),
        )

        cls.course = Course.objects.create(
            code='OTR201', title='Other Dept Course', credit_units=3, level=Level.LEVEL_100,
            department=cls.other_dept, semester_name=SemesterName.FIRST,
        )

    def test_course_offering_form_offers_lecturers_outside_the_department(self):
        from apps.courses.forms import CourseOfferingForm

        form = CourseOfferingForm(department=self.other_dept)

        self.assertIn(self.visiting_lecturer, form.fields['lecturer'].queryset)

    def test_hod_can_assign_a_lecturer_from_another_department(self):
        client = Client()
        self.assertTrue(client.login(username='otr.hod', password='hodpass123'))

        response = client.post(
            reverse('courses:course_offering_create'),
            {'course': str(self.course.pk), 'lecturer': str(self.visiting_lecturer.pk), 'capacity': 40},
            follow=True,
        )

        self.assertContains(response, 'assigned for')
        offering = CourseOffering.objects.get(course=self.course, semester=self.semester)
        self.assertEqual(offering.lecturer_id, self.visiting_lecturer.pk)

    def test_visiting_lecturer_surfaces_on_the_hosting_departments_dashboard(self):
        CourseOffering.objects.create(
            course=self.course, semester=self.semester, lecturer=self.visiting_lecturer, capacity=40,
        )

        client = Client()
        self.assertTrue(client.login(username='otr.hod', password='hodpass123'))
        response = client.get(reverse('dashboard:hod'))

        self.assertContains(response, 'Visiting Lecturers')
        self.assertContains(response, self.visiting_user.get_full_name())
        self.assertContains(response, 'HOM')

    def test_lecturer_own_courses_view_is_not_restricted_to_home_department(self):
        CourseOffering.objects.create(
            course=self.course, semester=self.semester, lecturer=self.visiting_lecturer, capacity=40,
        )

        client = Client()
        self.assertTrue(client.login(username='home.lecturer', password='lecpass123'))
        response = client.get(reverse('results:lecturer_offerings'))

        self.assertContains(response, 'OTR201')
