import uuid

from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    """Abstract base model using a UUID primary key instead of a
    sequential integer. Prevents enumeration of records (students,
    invoices, results, etc.) via predictable IDs in URLs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Abstract base model providing created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        """Bulk soft-delete: flips the flag instead of issuing DELETE."""
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Bulk permanent delete. Use only for genuine cleanup (e.g. GDPR)."""
        return super().delete()

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Default manager: only ever sees non-deleted rows."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class SoftDeleteModel(models.Model):
    """Abstract base model that replaces hard deletes with an is_deleted
    flag, so records like students, courses, departments, and payments
    can be archived and restored instead of destroyed.

    ``objects`` (the default manager) only returns non-deleted rows, so
    existing code that calls ``Model.objects.all()`` is unaffected.
    ``all_objects`` bypasses the filter for admin screens and reports
    that need to see archived records too.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False):
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])


class BaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """Standard base for all domain models in this project: UUID primary
    key, created/updated timestamps, and soft delete. New models in
    students, courses, departments, finance, results, etc. should inherit
    from this unless they have a specific reason not to (e.g. pure
    log/audit tables that should never be "undeleted").
    """

    class Meta:
        abstract = True
        ordering = ['-created_at']


class GlobalPermission(models.Model):
    """Anchor model with no database table, existing solely to hold
    business-action permissions that don't map to CRUD on a single
    domain model (e.g. "publish results" touches many Result rows across
    many students at once). This is Django's documented pattern for
    permissions not tied to one model - see "Custom permissions" in the
    Django auth docs.

    Real per-model CRUD permissions (add/change/delete/view Course, etc.)
    still come from each model as normal; this is only for the extra
    named actions the master plan's Business Rules call out, e.g.
    "Only Exam Officer publishes results."
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            # HOD
            ('can_assign_courses', 'Can assign courses to lecturers'),
            ('can_approve_registration', 'Can approve student course registration'),
            ('can_review_grades', 'Can review lecturer-submitted grades'),
            # Bursar
            ('can_verify_payment', 'Can verify student payments'),
            # Exam Officer
            ('can_compile_results', 'Can compile results'),
            ('can_publish_results', 'Can publish results'),
            ('can_generate_transcript', 'Can generate student transcripts'),
            # Registrar
            ('can_approve_admission', 'Can approve student admission'),
            ('can_generate_matric_numbers', 'Can generate matric numbers'),
            ('can_activate_semester', 'Can activate an academic semester'),
        ]
