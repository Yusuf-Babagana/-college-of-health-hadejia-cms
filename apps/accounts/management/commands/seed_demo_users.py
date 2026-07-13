from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.core.constants import Role

DEMO_USERS = [
    ('student1', Role.STUDENT, 'Amina', 'Yusuf'),
    ('lecturer1', Role.LECTURER, 'Bello', 'Ahmad'),
    ('hod1', Role.HOD, 'Fatima', 'Sani'),
    ('registrar1', Role.REGISTRAR, 'Ibrahim', 'Musa'),
    ('bursar1', Role.BURSAR, 'Halima', 'Garba'),
    ('examofficer1', Role.EXAM_OFFICER, 'Sadiq', 'Umar'),
    ('ictadmin1', Role.ICT_ADMIN, 'Zainab', 'Kabir'),
    ('superadmin1', Role.SUPER_ADMIN, 'Aisha', 'Bello'),
]


class Command(BaseCommand):
    help = 'Seed one demo user per role for manual QA (development only).'

    def handle(self, *args, **options):
        for username, role, first, last in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@coihst.edu.ng',
                    'first_name': first,
                    'last_name': last,
                    'role': role,
                },
            )
            if created:
                user.set_password('Password@123')
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Created {username} ({role})'))
            else:
                self.stdout.write(f'Already exists: {username}')
