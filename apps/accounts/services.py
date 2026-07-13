"""
Business logic for account/profile/password operations. Views stay thin
and call these; they own request/response plumbing only.
"""
import secrets

from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError

from .models import User


def create_user(*, username, email, first_name, last_name, role, phone_number='', password=None):
    """Provision a new account (any role).

    If ``password`` is given, the ICT Admin has chosen it themselves and is
    responsible for handing it to the new user. Otherwise a random
    temporary password is generated and returned so the caller (view) can
    show it exactly once - it is not stored anywhere in plain text.

    Either way, must_change_password forces the owner to set their own
    password on first login: a password someone else knows shouldn't
    remain valid indefinitely.
    """
    is_generated = not password
    if is_generated:
        password = secrets.token_urlsafe(9)

    user = User.objects.create_user(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        phone_number=phone_number,
        password=password,
        must_change_password=True,
    )
    return user, (password if is_generated else None)


def deactivate_user(user, *, acting_user):
    """Soft-disable an account: blocks login without deleting any data.

    Deliberately only touches is_active_account, not Django's own
    is_active: ModelBackend.authenticate() rejects is_active=False before
    StyledAuthenticationForm.confirm_login_allowed ever runs, which would
    replace our friendly "contact the ICT Administrator" message with
    Django's generic "incorrect username/password". is_active_account is
    checked in confirm_login_allowed, so the account is still fully
    blocked from logging in, just with a clearer message.
    """
    if user.pk == acting_user.pk:
        raise ValidationError('You cannot deactivate your own account.')

    user.is_active_account = False
    user.save(update_fields=['is_active_account'])
    return user


def reactivate_user(user):
    user.is_active_account = True
    user.save(update_fields=['is_active_account'])
    return user


def complete_password_change(request, form):
    """Persist a new password from a validated PasswordChangeForm.

    Refreshes the session hash so the user isn't logged out by their own
    password change, and clears must_change_password if it was set (e.g.
    after an ICT Admin-issued temporary password).
    """
    user = form.save()
    update_session_auth_hash(request, user)

    if user.must_change_password:
        user.must_change_password = False
        user.save(update_fields=['must_change_password'])

    return user
