"""
Companion to apps.courses.management.commands.tag_course_programme, for
the other half of the same problem: get_master_broadsheet's rows are now
students whose OWN Student.programme matches the selected Programme -
correct (a person only belongs to one programme), but it means a
student with no Programme assigned on their record won't appear on ANY
Master Broadsheet. Existing students almost certainly predate the
Programme field, so this bulk-assigns a whole department/level cohort
at once instead of editing students one at a time.

Usage examples (run on the server, e.g. the PythonAnywhere console) -
ALWAYS run with --dry-run first and read the printed list carefully
before dropping it; a department/level filter matches every student
meeting it, which - on a real database - means real students:

    # Preview which students in one department+level with no Programme
    # yet would be tagged
    python manage.py assign_student_programme --department <DEPT_CODE> --level <LEVEL> \
        --programme <PROGRAMME_CODE> --dry-run

    # Actually assign them, once the preview looks right
    python manage.py assign_student_programme --department <DEPT_CODE> --level <LEVEL> \
        --programme <PROGRAMME_CODE>

    # One specific student by matric number
    python manage.py assign_student_programme --matric <MATRIC_NUMBER> --programme <PROGRAMME_CODE>

    # Re-assign students that already have a (wrong) Programme set -
    # requires --force; without it, already-assigned students are
    # always left alone
    python manage.py assign_student_programme --department <DEPT_CODE> --programme <PROGRAMME_CODE> --force

Use `python manage.py inspect_student_programmes` first to see exactly
who currently has no Programme assigned before choosing filters here.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        'Bulk-assign a Programme to existing students who don\'t have one yet '
        '(or, with --force, re-assign students that already have one) - filter by '
        'department/level, or target one student by matric number.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--programme', required=True, help='Programme short_code to assign, e.g. SCHEW.',
        )
        parser.add_argument('--department', default=None, help='Department code to filter by, e.g. CHE.')
        parser.add_argument('--level', type=int, default=None, help='Level to filter by, e.g. 100.')
        parser.add_argument('--matric', default=None, help='Target exactly one student by matric number.')
        parser.add_argument(
            '--force', action='store_true',
            help='Also reassign students that already have a different Programme set. '
                 'Without this, students with a Programme already assigned are left alone.',
        )
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving.')

    def handle(self, *args, **options):
        from apps.admissions.models import Programme
        from apps.departments.models import Department
        from apps.students.models import Student

        prog_code = options['programme'].strip().upper()
        try:
            programme = Programme.objects.get(short_code__iexact=prog_code)
        except Programme.DoesNotExist:
            raise CommandError(f'No programme with short_code "{prog_code}" found.')

        if not options['matric'] and not options['department'] and options['level'] is None:
            raise CommandError('Give --matric for one student, or at least --department/--level to filter a cohort.')

        qs = Student.objects.select_related('user', 'department', 'programme')

        if options['matric']:
            matric = options['matric'].strip().upper()
            qs = qs.filter(matric_number=matric)
            if not qs.exists():
                raise CommandError(f'No student with matric number "{matric}" found.')
        else:
            if options['department']:
                dept_code = options['department'].strip().upper()
                try:
                    department = Department.objects.get(code=dept_code)
                except Department.DoesNotExist:
                    raise CommandError(f'No department with code "{dept_code}" found.')
                qs = qs.filter(department=department)
            if options['level'] is not None:
                qs = qs.filter(level=options['level'])

        if not options['force']:
            qs = qs.filter(programme__isnull=True)

        students = list(qs.order_by('matric_number'))
        already_correct = [s for s in students if s.programme_id == programme.pk]
        to_update = [s for s in students if s.programme_id != programme.pk]

        if not to_update:
            self.stdout.write('No students need updating (already assigned, or none matched the filters).')
            if already_correct:
                self.stdout.write(f'{len(already_correct)} already correctly set to {programme}.')
            return

        self.stdout.write(f'{"Would assign" if options["dry_run"] else "Assigning"} {programme} to {len(to_update)} student(s):')
        for student in to_update:
            previous = student.programme or 'None'
            self.stdout.write(f'  {student.matric_number} - {student.user.get_full_name()} ({previous} -> {programme})')

        if not options['dry_run']:
            for student in to_update:
                student.programme = programme
            with transaction.atomic():
                Student.objects.bulk_update(to_update, ['programme'])
            self.stdout.write(self.style.SUCCESS(f'Updated {len(to_update)} student(s).'))
        else:
            self.stdout.write(self.style.WARNING('Dry run - nothing was saved.'))
