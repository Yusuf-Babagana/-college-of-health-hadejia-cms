"""
Events that create a billing obligation. Finance listens so the apps that
own those events (academics, students) never need to know about invoices.
Every handler runs after the transaction commits and goes through the one
invoice-issuing service, so it is idempotent - re-delivery never
double-bills.
"""
import logging

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import services

logger = logging.getLogger('apps')

LevelSemesterState = django_apps.get_model('academics', 'LevelSemesterState')
Student = django_apps.get_model('students', 'Student')

# Student fields that change which fees apply to them.
_BILLING_FIELDS = {'department', 'department_id', 'programme', 'programme_id', 'level', 'status'}


@receiver(post_save, sender=LevelSemesterState)
@receiver(post_delete, sender=LevelSemesterState)
def bill_level_when_semester_changes(sender, instance, **kwargs):
    """A level (optionally one programme) opened or re-opened a semester:
    bill its students for that semester's published fees."""
    level, programme_id = instance.level, instance.programme_id
    transaction.on_commit(lambda: services.generate_invoices_for_level(level, programme_id))


@receiver(post_save, sender=Student)
def bill_student_when_enrolled_or_moved(sender, instance, created, update_fields=None, **kwargs):
    """A student was admitted, moved level/programme/department, or
    (re)activated: bill them for the fees that now apply."""
    if not created and update_fields is not None and not _BILLING_FIELDS & set(update_fields):
        return
    student_pk = instance.pk

    def _bill():
        student = Student.objects.filter(pk=student_pk).first()
        if student:
            services.sync_invoices_for_student(student)

    transaction.on_commit(_bill)
