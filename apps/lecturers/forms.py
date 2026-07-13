from django import forms

from apps.core.forms import CrispyFormMixin
from apps.departments.models import Department

from . import selectors
from .models import Lecturer


class LecturerCreateForm(CrispyFormMixin, forms.Form):
    """Plain Form, not ModelForm: user choices must be restricted to
    lecturer-role accounts without an existing profile, which is a query,
    not something a ModelForm's field can express declaratively.
    """
    submit_label = 'Create Lecturer Profile'

    user = forms.ModelChoiceField(queryset=None, label='User Account')
    department = forms.ModelChoiceField(queryset=Department.objects.all())
    qualification = forms.CharField(max_length=150, required=False)
    specialization = forms.CharField(max_length=150, required=False)
    appointment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = selectors.get_lecturer_role_users_without_profile()
        self.fields['user'].help_text = (
            'Only shows users with the Lecturer role that don\'t already have a profile. '
            'Create the user account first under Manage Users if it\'s not listed.'
        )


class LecturerUpdateForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Changes'

    class Meta:
        model = Lecturer
        fields = ('department', 'qualification', 'specialization', 'appointment_date')
        widgets = {
            'appointment_date': forms.DateInput(attrs={'type': 'date'}),
        }
