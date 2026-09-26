"""
One-off data-fixing tool for a course that predates the Programme field,
or was never tagged, and so is invisible on every programme's Master
Broadsheet even though students are legitimately registered for it.
Works purely from whatever course/department/programme codes actually
exist in the database - it has no built-in notion of any specific
course or programme.

Usage examples (run on the server, e.g. the PythonAnywhere console):

    # Set a course's primary Programme, and cross-list it to a second one
    python manage.py tag_course_programme <COURSE_CODE> \
        --programme <PRIMARY_PROGRAMME_CODE> \
        --eligible <PRIMARY_PROGRAMME_CODE> --eligible <OTHER_PROGRAMME_CODE>

    # Move a course to the right department first, then tag it
    python manage.py tag_course_programme <COURSE_CODE> \
        --department <DEPARTMENT_CODE> --programme <PROGRAMME_CODE>

    # Preview only, no changes saved
    python manage.py tag_course_programme <COURSE_CODE> --programme <PROGRAMME_CODE> --dry-run

Programme/department are matched by their short_code/code (case
-insensitive) - use `python manage.py inspect_course_programme_links`
(or `python manage.py shell -c "from apps.admissions.models import
Programme; [print(p.short_code, p.name) for p in Programme.objects.all()]"`)
first if you're not sure of the exact short_code.
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction


class Command(BaseCommand):
    help = (
        'Set a course\'s primary Programme, its Eligible Programmes (cross-listing), '
        'and optionally reassign its Department - the fix for a course that predates '
        'the Programme field and is invisible on every Master Broadsheet as a result.'
    )

    def add_arguments(self, parser):
        parser.add_argument('code', help='Course code, e.g. CHE113 (case-insensitive).')
        parser.add_argument(
            '--department', default=None,
            help='Department code to move this course under first, if it\'s not already there, e.g. CHE.',
        )
        parser.add_argument(
            '--programme', default=None,
            help='Programme short_code to set as this course\'s primary Programme, e.g. DCH.',
        )
        parser.add_argument(
            '--eligible', action='append', default=[],
            help='Programme short_code to add to Eligible Programmes (cross-listing). '
                 'Repeatable, e.g. --eligible DCH --eligible CCH. Additive - existing '
                 'entries are kept, not replaced.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would change without saving anything.',
        )

    def handle(self, *args, **options):
        from apps.admissions.models import Programme
        from apps.courses.models import Course
        from apps.departments.models import Department

        code = options['code'].strip().upper()
        try:
            course = Course.objects.get(code=code)
        except Course.DoesNotExist:
            raise CommandError(f'No course with code "{code}" found.')

        dry_run = options['dry_run']
        changes = []

        if options['department']:
            dept_code = options['department'].strip().upper()
            try:
                department = Department.objects.get(code=dept_code)
            except Department.DoesNotExist:
                raise CommandError(f'No department with code "{dept_code}" found.')
            if department.pk != course.department_id:
                changes.append(f'department: {course.department} -> {department}')
                course.department = department

        if options['programme']:
            prog_code = options['programme'].strip().upper()
            try:
                programme = Programme.objects.get(short_code__iexact=prog_code)
            except Programme.DoesNotExist:
                raise CommandError(f'No programme with short_code "{prog_code}" found.')
            if programme.pk != course.programme_id:
                changes.append(f'programme: {course.programme} -> {programme}')
                course.programme = programme

        if changes:
            try:
                course.full_clean()
            except DjangoValidationError as exc:
                raise CommandError(f'Validation failed: {exc.message_dict}')

        eligible_to_add = []
        for prog_code in options['eligible']:
            prog_code = prog_code.strip().upper()
            try:
                programme = Programme.objects.get(short_code__iexact=prog_code)
            except Programme.DoesNotExist:
                raise CommandError(f'No programme with short_code "{prog_code}" found.')
            if not course.eligible_programmes.filter(pk=programme.pk).exists():
                eligible_to_add.append(programme)

        # Every resolution/validation step above only reads and raises -
        # nothing is written until here, and the FK change (course.save())
        # plus the M2M change (eligible_programmes.add()) happen together
        # in one transaction so a failure partway through can't leave the
        # course half-tagged.
        if not dry_run and (changes or eligible_to_add):
            with transaction.atomic():
                if changes:
                    course.save()
                if eligible_to_add:
                    course.eligible_programmes.add(*eligible_to_add)

        self.stdout.write(self.style.SUCCESS(f'Course: {course.code} - {course.title}'))
        if not changes and not eligible_to_add:
            self.stdout.write('No changes needed - already tagged as requested.')
            return

        for line in changes:
            self.stdout.write(f'  {line}')
        for programme in eligible_to_add:
            self.stdout.write(f'  + eligible_programmes: {programme}')

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run - nothing was saved.'))
        else:
            self.stdout.write(self.style.SUCCESS('Saved.'))
