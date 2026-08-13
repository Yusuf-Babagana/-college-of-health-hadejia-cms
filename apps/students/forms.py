from django import forms

from apps.core.constants import Level
from apps.core.forms import CrispyFormMixin, DepartmentScopedSelect
from apps.core.utils.validators import matric_number_validator, phone_number_validator

from .models import Student


class StudentCreateForm(CrispyFormMixin, forms.Form):
    """One combined "Add Student" form: the account and the academic
    profile are created together by services.create_student - which is
    why this is a plain Form, not a ModelForm over Student. The matric
    number can be typed in (e.g. transferring in an existing number) or
    left blank to auto-generate the next one in the department + year
    sequence.
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
        max_length=30, required=False,
        help_text='e.g. CHE/2025/0005. Leave blank to auto-generate the next number '
                  'for the chosen department and admission session.',
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
        # Uppercase before validating, so 'che/2025/0005' is accepted -
        # a field-level validator would run against the raw input.
        matric_number = (self.cleaned_data.get('matric_number') or '').strip().upper()
        if matric_number:
            matric_number_validator(matric_number)
            if Student.all_objects.filter(matric_number=matric_number).exists():
                raise forms.ValidationError('A student with this matric number already exists.')
        return matric_number


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
