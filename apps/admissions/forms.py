from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.forms import inlineformset_factory

from apps.accounts.models import User
from apps.core.forms import CrispyFormMixin
from apps.core.utils.validators import phone_number_validator

from .models import (
    Application,
    Programme,
    SchoolAttended,
    SSCESitting,
    SSCESubjectResult,
    UploadedDocument,
)


class ApplicantSignupForm(CrispyFormMixin, forms.Form):
    """Not a ModelForm - creates the User, Applicant, and Application rows
    together in apps.admissions.views.SignupView, which needs to hash the
    password and wire up the related rows in one transaction.
    """
    submit_label = 'Create My Account'

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone_number = forms.CharField(max_length=15, validators=[phone_number_validator])
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The two password fields did not match.')
            return cleaned_data

        if password1:
            try:
                validate_password(password1)
            except DjangoValidationError as exc:
                self.add_error('password1', exc)

        return cleaned_data


class ApplicantLoginForm(CrispyFormMixin, forms.Form):
    submit_label = 'Sign In'

    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


class ReferralCodeForm(CrispyFormMixin, forms.Form):
    submit_label = 'Apply Code'

    code = forms.CharField(max_length=20, label='Referral Code')


class SectionAForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save & Continue'

    class Meta:
        model = Application
        fields = [
            'date_of_birth', 'gender', 'state_of_origin', 'lga_of_origin', 'home_address',
            'guardian_name', 'guardian_phone', 'guardian_address',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'home_address': forms.Textarea(attrs={'rows': 2}),
            'guardian_address': forms.Textarea(attrs={'rows': 2}),
        }


class SchoolAttendedForm(forms.ModelForm):
    class Meta:
        model = SchoolAttended
        fields = ['school_name', 'qualification', 'start_year', 'end_year']
        widgets = {
            'school_name': forms.TextInput(attrs={'class': 'form-control'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control'}),
            'start_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'end_year': forms.NumberInput(attrs={'class': 'form-control'}),
        }


SchoolAttendedFormSet = inlineformset_factory(
    Application, SchoolAttended, form=SchoolAttendedForm,
    extra=3, max_num=3, can_delete=False,
)


class SSCESittingForm(forms.ModelForm):
    class Meta:
        model = SSCESitting
        fields = ['exam_type', 'exam_year', 'exam_number']
        widgets = {
            'exam_type': forms.Select(attrs={'class': 'form-select'}),
            'exam_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'exam_number': forms.TextInput(attrs={'class': 'form-control'}),
        }


class SSCESubjectResultForm(forms.ModelForm):
    class Meta:
        model = SSCESubjectResult
        fields = ['subject_name', 'grade']
        widgets = {
            'subject_name': forms.TextInput(attrs={'class': 'form-control'}),
            'grade': forms.TextInput(attrs={'class': 'form-control'}),
        }


SSCESubjectResultFormSet = inlineformset_factory(
    SSCESitting, SSCESubjectResult, form=SSCESubjectResultForm,
    extra=9, max_num=9, can_delete=True,
)


class SectionDForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save & Continue'

    class Meta:
        model = Application
        fields = ['programme_first_choice', 'programme_second_choice']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_programmes = Programme.objects.filter(is_active=True)
        self.fields['programme_first_choice'].queryset = active_programmes
        self.fields['programme_second_choice'].queryset = active_programmes
        self.fields['programme_second_choice'].required = False

    def clean(self):
        cleaned_data = super().clean()
        first = cleaned_data.get('programme_first_choice')
        second = cleaned_data.get('programme_second_choice')
        if first and second and first == second:
            self.add_error('programme_second_choice', 'Second choice must differ from your first choice.')
        return cleaned_data


class SectionEForm(forms.ModelForm):
    """Rendered with {{ form|crispy }} inside a hand-written <form> tag
    (templates/admissions/section_e.html) so the document formset can share
    the same submit button - form_tag=False and no auto-added Submit input,
    unlike CrispyFormMixin's default.
    """

    class Meta:
        model = Application
        fields = ['passport_photo', 'declaration_accepted']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from crispy_forms.helper import FormHelper
        self.helper = FormHelper()
        self.helper.form_tag = False

    def clean_declaration_accepted(self):
        accepted = self.cleaned_data['declaration_accepted']
        if not accepted:
            raise forms.ValidationError('You must accept the declaration to proceed.')
        return accepted


class UploadedDocumentForm(forms.ModelForm):
    class Meta:
        model = UploadedDocument
        fields = ['document_type', 'file']
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


UploadedDocumentFormSet = inlineformset_factory(
    Application, UploadedDocument, form=UploadedDocumentForm,
    extra=3, can_delete=True,
)
