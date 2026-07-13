"""
Business logic for lecturer profile management.
"""
from .models import Lecturer


def create_lecturer_profile(*, user, department, qualification, specialization, appointment_date):
    lecturer = Lecturer(
        user=user,
        department=department,
        qualification=qualification,
        specialization=specialization,
        appointment_date=appointment_date,
    )
    lecturer.full_clean()
    lecturer.save()
    return lecturer


def archive_lecturer(lecturer):
    lecturer.delete()  # soft delete
    return lecturer


def restore_lecturer(lecturer):
    lecturer.restore()
    return lecturer
