from django.core.management.base import BaseCommand

from apps.courses import services


class Command(BaseCommand):
    help = (
        'Offers every course that has no programme of its own (General Studies, department-wide '
        'courses) in each programme\'s currently running semester, mirroring the offerings that '
        'already exist. Idempotent; archived offerings are never resurrected. Use --dry-run to see '
        'what would be created.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='List what would be created; change nothing.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        report = services.sync_shared_course_offerings(dry_run=dry_run)
        total = 0
        for offering, added in report:
            where = ', '.join(str(item if dry_run else item.semester) for item in added)
            self.stdout.write(f'{offering.course.code} ({offering.course.title}): {where}')
            total += len(added)
        verb = 'Would create' if dry_run else 'Created'
        self.stdout.write(self.style.SUCCESS(f'{verb} {total} offering(s) across {len(report)} course(s).'))
