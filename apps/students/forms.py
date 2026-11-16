from datetime import date

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row
from django import forms

from apps.admissions.models import Programme
from apps.core.constants import Level
from apps.core.forms import CrispyFormMixin, DepartmentScopedSelect
from apps.accounts.models import User
from apps.core.utils.validators import phone_number_validator, validate_image_file

from .models import Guardian, Student


class StudentCreateForm(CrispyFormMixin, forms.Form):
    """One combined "Add Student" form: the account and the academic
    profile are created together by services.create_student - which is
    why this is a plain Form, not a ModelForm over Student. The matric
    number has no fixed format - the Registrar types in whatever number
    was assigned, and only uniqueness is enforced here.
    """
    submit_label = 'Create Student'

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone_number = forms.CharField(max_length=15, required=False, validators=[phone_number_validator])
    department = forms.ModelChoiceField(queryset=None)
    programme = forms.ModelChoiceField(
        queryset=None, required=False,
        help_text='Choose the Department above first - Programme narrows to match it.',
    )
    level = forms.TypedChoiceField(choices=Level.choices, coerce=int, initial=Level.LEVEL_100)
    admission_session = forms.ModelChoiceField(queryset=None)
    matric_number = forms.CharField(
        max_length=30,
        help_text='Assigned by the Registrar - no fixed format, but it must be unique.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.academics.selectors import get_active_sessions
        from apps.admissions.models import Programme
        from apps.departments.selectors import get_active_departments

        self.fields['department'].queryset = get_active_departments()
        self.fields['admission_session'].queryset = get_active_sessions()

        programme_qs = Programme.objects.filter(is_active=True)
        self.fields['programme'].queryset = programme_qs
        self.fields['programme'].widget = DepartmentScopedSelect(
            attrs={'data-scoped-by': 'department'},
            department_by_value={
                str(pk): str(department_id)
                for pk, department_id in programme_qs.values_list('pk', 'department_id')
            },
        )
        self.fields['programme'].widget.choices = self.fields['programme'].choices

    def clean_matric_number(self):
        matric_number = self.cleaned_data.get('matric_number', '').strip()
        if Student.all_objects.filter(matric_number=matric_number).exists():
            raise forms.ValidationError('A student with this matric number already exists.')
        return matric_number


class BulkPromotionForm(CrispyFormMixin, forms.Form):
    """Pick which students to move up: every active student at a level,
    optionally narrowed to one programme."""
    submit_label = 'Preview Promotion'

    level = forms.TypedChoiceField(
        choices=Level.choices, coerce=int, label='Promote students currently in',
    )
    programme = forms.ModelChoiceField(
        queryset=Programme.objects.none(), required=False, empty_label='All programmes',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programme'].queryset = Programme.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        programme, level = cleaned.get('programme'), cleaned.get('level')
        if programme and level and level not in programme.levels:
            self.add_error('level', f'{programme} does not have a {dict(Level.choices)[level]}.')
        return cleaned


class StudentStatusForm(CrispyFormMixin, forms.Form):
    """Focused, single-purpose form for FR-REG-05 - deliberately not a
    ModelForm on the whole Student record, since status changes are a
    distinct action from editing department/level.
    """
    submit_label = 'Update Status'

    status = forms.ChoiceField(choices=Student.Status.choices)


class StudentProfileForm(CrispyFormMixin, forms.ModelForm):
    """Editing department/level for an already-admitted student - not an
    admission action, just ongoing profile maintenance.
    """
    submit_label = 'Save Changes'

    class Meta:
        model = Student
        fields = ('department', 'programme', 'level')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programme'].queryset = self.fields['programme'].queryset.filter(is_active=True)


# --- Student self-service profile: three sections saved together ---------


class _SectionFormMixin:
    """A form that renders as one card of a larger <form> - no <form> tag,
    CSRF token or submit button of its own (the page supplies those)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True


def _two_columns(*names):
    """Layout rows of two fields each."""
    rows = [
        Row(*[Column(name, css_class='col-md-6') for name in names[i:i + 2]])
        for i in range(0, len(names), 2)
    ]
    return Layout(*rows)


class StudentAccountForm(_SectionFormMixin, forms.ModelForm):
    """Contact details and the profile picture. The picture is handled by
    services.update_profile_photo, not by this ModelForm."""

    photo = forms.ImageField(
        required=False, label='Profile picture', widget=forms.FileInput(attrs={'accept': 'image/*'}),
        help_text='A clear, front-facing passport-style photo. JPG, PNG or WebP, up to 2 MB. '
                  'It is printed on your Course Registration Form.',
    )

    class Meta:
        model = User
        fields = ('email', 'phone_number')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['phone_number'].required = True
        self.helper.layout = Layout('photo', *[
            Row(Column('email', css_class='col-md-6'), Column('phone_number', css_class='col-md-6')),
        ])

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            validate_image_file(photo)
        return photo


class StudentPersonalForm(_SectionFormMixin, forms.ModelForm):
    class Meta:
        model = Student
        fields = (
            'date_of_birth', 'gender', 'marital_status', 'religion', 'nationality',
            'state_of_origin', 'lga_of_origin', 'blood_group', 'genotype', 'home_address',
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'home_address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('date_of_birth', 'gender', 'state_of_origin', 'home_address'):
            self.fields[name].required = True
        if not self.instance.nationality:
            self.initial['nationality'] = 'Nigerian'  # a suggestion, confirmed on save
        self.helper.layout = Layout(
            Row(Column('date_of_birth', css_class='col-md-6'), Column('gender', css_class='col-md-6')),
            Row(Column('marital_status', css_class='col-md-6'), Column('religion', css_class='col-md-6')),
            Row(Column('nationality', css_class='col-md-6'), Column('state_of_origin', css_class='col-md-6')),
            Row(Column('lga_of_origin', css_class='col-md-6')),
            Row(Column('blood_group', css_class='col-md-6'), Column('genotype', css_class='col-md-6')),
            'home_address',
        )

    def clean_date_of_birth(self):
        born = self.cleaned_data.get('date_of_birth')
        if born:
            today = date.today()
            age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
            if born > today:
                raise forms.ValidationError('Date of birth cannot be in the future.')
            if not 10 <= age <= 90:
                raise forms.ValidationError('Please check the date of birth - it gives an age of %d.' % age)
        return born


class GuardianForm(_SectionFormMixin, forms.ModelForm):
    class Meta:
        model = Guardian
        fields = ('full_name', 'relationship', 'phone_number', 'email', 'occupation', 'address')
        labels = {'full_name': 'Full name', 'phone_number': 'Phone number', 'email': 'Email (optional)'}
        widgets = {'address': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            Row(Column('full_name', css_class='col-md-6'), Column('relationship', css_class='col-md-6')),
            Row(Column('phone_number', css_class='col-md-6'), Column('email', css_class='col-md-6')),
            'occupation',
            'address',
        )
