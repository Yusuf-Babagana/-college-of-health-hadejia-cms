"""
Read-only audit of Course <-> Programme data quality. Makes ZERO
database writes - safe to run against production at any time, including
directly against the live PythonAnywhere database, to get real numbers
back instead of guessing.

Reports, optionally scoped by --department:
  - courses with a primary Programme set
  - courses cross-listed via eligible_programmes
  - courses with NEITHER (the "No Programme" bucket) - split into
    "blanket-eligible" (their department is flagged General Studies, so
    they're automatically visible on every programme's broadsheet
    despite having no explicit tagging) vs. "ORPHANED" (an ordinary
    department, not General Studies - genuinely invisible on every
    Master Broadsheet until tagged one way or the other)
  - courses whose primary Programme's Department doesn't match the
    course's own Department (a likely data-entry mistake)
  - a summary of every General Studies department and its courses

Usage:
    python manage.py inspect_course_programme_links
    python manage.py inspect_course_programme_links --department CHE
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Read-only report on Course/Programme data quality. Makes no database writes.'

    def add_arguments(self, parser):
        parser.add_argument('--department', default=None, help='Department code to scope the report to, e.g. CHE.')

    def handle(self, *args, **options):
        from apps.courses.models import Course
        from apps.departments.models import Department

        qs = Course.objects.select_related('department', 'programme', 'programme__department').prefetch_related(
            'eligible_programmes',
        )

        if options['department']:
            dept_code = options['department'].strip().upper()
            try:
                department = Department.objects.get(code=dept_code)
            except Department.DoesNotExist:
                raise CommandError(f'No department with code "{dept_code}" found.')
            qs = qs.filter(department=department)

        courses = list(qs.order_by('code'))
        w = self.stdout.write

        w(self.style.MIGRATE_HEADING(f'Course/Programme report ({len(courses)} course(s) in scope)'))
        w('')

        with_primary = [c for c in courses if c.programme_id]
        w(self.style.MIGRATE_HEADING(f'Courses with a primary Programme: {len(with_primary)}'))
        for c in with_primary:
            w(f'  {c.code} ({c.title}) -> {c.programme.name}')
        if not with_primary:
            w('  (none)')
        w('')

        cross_listed = [c for c in courses if c.eligible_programmes.exists()]
        w(self.style.MIGRATE_HEADING(f'Courses cross-listed via Eligible Programmes: {len(cross_listed)}'))
        for c in cross_listed:
            names = ', '.join(p.name for p in c.eligible_programmes.all())
            w(f'  {c.code} ({c.title}) -> also: {names}')
        if not cross_listed:
            w('  (none)')
        w('')

        untagged = [c for c in courses if not c.programme_id and not c.eligible_programmes.exists()]
        blanket = [c for c in untagged if c.department.is_general_studies]
        orphaned = [c for c in untagged if not c.department.is_general_studies]

        w(self.style.MIGRATE_HEADING(f'No Programme tagging at all: {len(untagged)}'))
        w(f'  Blanket-eligible (General Studies department, visible on every broadsheet): {len(blanket)}')
        for c in blanket:
            w(f'    {c.code} ({c.title}) - {c.department.name}')
        w(self.style.WARNING(
            f'  ORPHANED (ordinary department, invisible on every Master Broadsheet until tagged): {len(orphaned)}',
        ))
        for c in orphaned:
            w(f'    {c.code} ({c.title}) - {c.department.name}')
        w('')

        dept_mismatches = [
            c for c in courses
            if c.programme_id and c.programme.department_id and c.programme.department_id != c.department_id
        ]
        w(self.style.MIGRATE_HEADING(f"Courses whose primary Programme's Department differs from their own: {len(dept_mismatches)}"))
        for c in dept_mismatches:
            w(f'  {c.code} - course dept={c.department.code}, programme "{c.programme.name}" dept={c.programme.department}')
        if not dept_mismatches:
            w('  (none)')
        w('')

        gst_departments = Department.objects.filter(is_general_studies=True)
        w(self.style.MIGRATE_HEADING(f'General Studies departments: {gst_departments.count()}'))
        for dept in gst_departments:
            dept_courses = [c for c in courses if c.department_id == dept.pk] or list(
                Course.objects.filter(department=dept).order_by('code'),
            )
            w(f'  {dept.name} ({dept.code}) - {len(dept_courses)} course(s)')
            for c in dept_courses:
                w(f'    {c.code} ({c.title})')
