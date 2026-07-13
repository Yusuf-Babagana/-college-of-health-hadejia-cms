from django.apps import apps as django_apps
from django.contrib.auth.models import Group
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from apps.core.constants import Role


@receiver(post_migrate)
def create_role_groups(sender, **kwargs):
    """Ensure a Django Group exists for every role in the system.

    Groups are the vehicle for Django's permission system; each role's
    group accumulates model permissions as the corresponding app is built
    out in later phases.
    """
    if sender.name != 'apps.accounts':
        return
    for role in Role:
        Group.objects.get_or_create(name=role.label)


@receiver(post_save, sender=django_apps.get_model('accounts', 'User'))
def sync_user_role_group(sender, instance, **kwargs):
    """Keep the user's group membership in sync with their role field."""
    role = Role(instance.role) if instance.role else None
    role_group_names = {r.label for r in Role}

    current_group_names = set(instance.groups.values_list('name', flat=True))
    stale = current_group_names & role_group_names - ({role.label} if role else set())
    if stale:
        instance.groups.remove(*Group.objects.filter(name__in=stale))

    if role and role.label not in current_group_names:
        group, _ = Group.objects.get_or_create(name=role.label)
        instance.groups.add(group)


@receiver(post_save, sender=django_apps.get_model('accounts', 'User'))
def grant_super_admin_staff_access(sender, instance, **kwargs):
    """Super Admin doubles as Django's own superuser concept - being
    assigned this role must actually unlock Django Admin, not just this
    project's own dashboard. Only grants, never revokes - if someone is
    demoted from Super Admin, an ICT Admin can explicitly strip
    is_staff/is_superuser via the user edit form if that's intended.
    """
    if instance.role == Role.SUPER_ADMIN and not (instance.is_staff and instance.is_superuser):
        sender.objects.filter(pk=instance.pk).update(is_staff=True, is_superuser=True)
