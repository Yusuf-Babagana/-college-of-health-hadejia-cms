from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import create_user
from apps.core.constants import Level, Role
from apps.core.utils.generators import generate_matric_number
from apps.departments.models import Department
from apps.academics.models import AcademicSession
from apps.students.models import Student

DEMO_STUDENTS = [
    ('student2', 'Amina', 'Bello', Level.LEVEL_100),
    ('student3', 'Bashir', 'Umar', Level.LEVEL_200),
]


class Command(BaseCommand):
    help = (
        'Seed a couple of demo students for manual QA (development only). '
        'Not a substitute for the real Admission portal - just test data.'
    )

    def handle(self, *args, **options):
        department = Department.objects.filter(code='CHE').first()
        if not department:
            raise CommandError('No department with code "CHE" found - create one first.')

        session = AcademicSession.objects.order_by('-name').first()
        if not session:
            raise CommandError('No academic session found - create one first.')

        for index, (username, first_name, last_name, level) in enumerate(DEMO_STUDENTS, start=1):
            if Student.objects.filter(user__username=username).exists():
                self.stdout.write(f'Already exists: {username}')
                continue

            user, password = create_user(
                username=username,
                email=f'{username}@coihst.edu.ng',
                first_name=first_name,
                last_name=last_name,
                role=Role.STUDENT,
            )
            matric_number = generate_matric_number(department.code, int(session.name[:4]), index)
            student = Student.objects.create(
                user=user,
                matric_number=matric_number,
                department=department,
                level=level,
                admission_session=session,
            )
            self.stdout.write(self.style.SUCCESS(
                f'Created {student.matric_number} ({username}), temp password: {password}',
            ))
