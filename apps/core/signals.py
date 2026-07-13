from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from apps.core.constants import ROLE_PERMISSIONS, Role


@receiver(post_migrate)
def assign_default_group_permissions(sender, **kwargs):
    """Grant each role's group its default custom permissions (see
    ROLE_PERMISSIONS / GlobalPermission).

    Filtered to fire on core's own post_migrate dispatch: Django connects
    django.contrib.auth's create_permissions receiver before this one
    (apps.core is registered after django.contrib.auth in INSTALLED_APPS),
    so by the time this runs, core's custom permissions already exist in
    the database for this exact dispatch - no dependency on the order
    other apps happen to migrate in.
    """
    if sender.name != 'apps.core':
        return

    for role in Role:
        codenames = ROLE_PERMISSIONS.get(role)
        if not codenames:
            continue

        group, _ = Group.objects.get_or_create(name=role.label)
        perms = []
        for codename in codenames:
            app_label, _, codename = codename.partition('.')
            try:
                perms.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
            except Permission.DoesNotExist:
                continue
        if perms:
            group.permissions.add(*perms)
