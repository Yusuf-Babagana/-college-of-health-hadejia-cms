"""
Read-only audit of Student <-> Programme data quality. Makes ZERO
database writes - safe to run against production at any time, including
directly against the live PythonAnywhere database, to get real numbers
back instead of guessing.

Reports, optionally scoped by --department/--level/--programme:
  - total students in scope, and how many have no Programme assigned
  - a breakdown of student counts per Programme
  - the actual list of students with no Programme (matric/name/dept/level),
    so you know exactly who assign_student_programme needs to cover
  - inconsistencies: a student's Department not matching their own
    Programme's Department; a student's Level falling outside their
    Programme's duration_levels
  - a summary of any cross-programme registration conflicts (students
    actively registered under courses from more than one Programme -
    see apps.courses.selectors.get_cross_programme_registration_conflicts,
    also browsable at /courses/registrations/conflicts/)

Usage:
    python manage.py inspect_student_programmes
    python manage.py inspect_student_programmes --department CHE
    python manage.py inspect_student_programmes --department CHE --level 100
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Read-only report on Student/Programme data quality. Makes no database writes.'

    def add_arguments(self, parser):
        parser.add_argument('--department', default=None, help='Department code to scope the report to, e.g. CHE.')
        parser.add_argument('--level', type=int, default=None, help='Level to scope the report to, e.g. 100.')
        parser.add_argument(
            '--programme', default=None, help='Programme short_code to scope the report to.',
        )

    def handle(self, *args, **options):
        from apps.admissions.models import Programme
        from apps.courses.selectors import get_cross_programme_registration_conflicts
        from apps.departments.models import Department
        from apps.students.models import Student

        qs = Student.objects.select_related('user', 'department', 'programme', 'programme__department')
        department = None

        if options['department']:
            dept_code = options['department'].strip().upper()
            try:
                department = Department.objects.get(code=dept_code)
            except Department.DoesNotExist:
                raise CommandError(f'No department with code "{dept_code}" found.')
            qs = qs.filter(department=department)

        if options['level'] is not None:
            qs = qs.filter(level=options['level'])

        if options['programme']:
            prog_code = options['programme'].strip().upper()
            try:
                programme = Programme.objects.get(short_code__iexact=prog_code)
            except Programme.DoesNotExist:
                raise CommandError(f'No programme with short_code "{prog_code}" found.')
            qs = qs.filter(programme=programme)

        students = list(qs.order_by('matric_number'))
        w = self.stdout.write

        w(self.style.MIGRATE_HEADING(f'Student/Programme report ({len(students)} student(s) in scope)'))
        w('')

        # --- No programme assigned ---
        no_programme = [s for s in students if s.programme_id is None]
        w(self.style.MIGRATE_HEADING(f'No Programme assigned: {len(no_programme)}'))
        for s in no_programme:
            w(f'  {s.matric_number} - {s.user.get_full_name()} | dept={s.department.code} | level={s.get_level_display()}')
        if not no_programme:
            w('  (none)')
        w('')

        # --- Breakdown by programme ---
        by_programme = {}
        for s in students:
            key = s.programme.name if s.programme else '(none)'
            by_programme[key] = by_programme.get(key, 0) + 1
        w(self.style.MIGRATE_HEADING('Breakdown by Programme'))
        for name, count in sorted(by_programme.items()):
            w(f'  {name}: {count}')
        w('')

        # --- Inconsistencies ---
        dept_mismatches = [
            s for s in students
            if s.programme_id and s.programme.department_id and s.programme.department_id != s.department_id
        ]
        level_mismatches = [
            s for s in students
            if s.programme_id and s.level not in s.programme.levels
        ]

        w(self.style.MIGRATE_HEADING(f'Department mismatches (student.department != programme.department): {len(dept_mismatches)}'))
        for s in dept_mismatches:
            w(f'  {s.matric_number} - student dept={s.department.code}, programme "{s.programme.name}" dept={s.programme.department}')
        if not dept_mismatches:
            w('  (none)')
        w('')

        w(self.style.MIGRATE_HEADING(f'Level mismatches (student.level outside programme.levels): {len(level_mismatches)}'))
        for s in level_mismatches:
            w(f'  {s.matric_number} - level={s.get_level_display()}, programme "{s.programme.name}" runs {s.programme.levels}')
        if not level_mismatches:
            w('  (none)')
        w('')

        # --- Cross-programme registration conflicts ---
        conflicts = get_cross_programme_registration_conflicts(department=department)
        w(self.style.MIGRATE_HEADING(f'Students registered across more than one Programme: {len(conflicts)}'))
        for entry in conflicts:
            student = entry['student']
            programmes = ', '.join(p.name for p in entry['programmes'])
            w(f'  {student.matric_number} - {student.user.get_full_name()} -> {programmes}')
        if not conflicts:
            w('  (none)')
        w('  (see /courses/registrations/conflicts/ in the app for full detail per student)')
