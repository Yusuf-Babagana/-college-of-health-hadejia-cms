from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.core.constants import Role
from apps.core.forms import CrispyFormMixin
from apps.core.utils.validators import phone_number_validator

from .models import User


class StyledAuthenticationForm(CrispyFormMixin, AuthenticationForm):
    submit_label = 'Sign In'

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_active_account:
            # is_active_account is the shared "portal access" flag for both
            # ICT Admin-deactivated staff accounts and non-Active student
            # statuses (suspended/withdrawn) - kept generic since either
            # case can land here.
            raise forms.ValidationError(
                'This account does not currently have portal access. '
                'Contact the Registrar or ICT Administrator.',
                code='inactive_account',
            )


class StyledPasswordChangeForm(CrispyFormMixin, PasswordChangeForm):
    submit_label = 'Change Password'


class StyledPasswordResetForm(CrispyFormMixin, PasswordResetForm):
    submit_label = 'Send Reset Link'


class StyledSetPasswordForm(CrispyFormMixin, SetPasswordForm):
    submit_label = 'Set New Password'


class ProfileUpdateForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Changes'

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone_number', 'avatar')


class AdminUserCreateForm(CrispyFormMixin, forms.Form):
    """Not a ModelForm: creating a user means hashing a generated password
    and setting must_change_password, which apps.accounts.services.create_user
    handles - this form only validates the input fields.
    """
    submit_label = 'Create User'

    # HOD is deliberately excluded: it's not a role you create someone
    # into directly - it's granted by assigning an existing Lecturer as
    # Department.hod (apps.departments.services.assign_hod), which also
    # promotes their role. Creating a "bare" HOD here would give someone
    # the HOD dashboard/permissions with no department attached.
    ASSIGNABLE_ROLES = [choice for choice in Role.choices if choice[0] != Role.HOD]

    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    role = forms.ChoiceField(
        choices=ASSIGNABLE_ROLES,
        help_text='To make someone Head of Department, create them as a Lecturer, '
                   'give them a Lecturer profile, then use "Assign HOD" on the department.',
    )
    phone_number = forms.CharField(
        max_length=15, required=False, validators=[phone_number_validator]
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput,
        required=False,
        help_text='Leave both password fields blank to auto-generate a secure '
                   'temporary password instead (shown once after creation).',
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput,
        required=False,
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('A user with this username already exists.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if not password1 and not password2:
            return cleaned_data

        if password1 != password2:
            self.add_error('password2', 'The two password fields did not match.')
            return cleaned_data

        try:
            validate_password(password1)
        except DjangoValidationError as exc:
            self.add_error('password1', exc)

        return cleaned_data


class AdminUserUpdateForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Changes'

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'role', 'phone_number')
        help_texts = {
            'role': 'To assign someone as Head of Department, use "Assign HOD" on the '
                    'Departments page instead of setting it here directly.',
        }
