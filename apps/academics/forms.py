from django import forms

from apps.core.constants import Level
from apps.core.forms import CrispyFormMixin

from apps.admissions.models import Programme

from .models import AcademicSession, Semester


class AcademicSessionForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Session'

    class Meta:
        model = AcademicSession
        fields = ('name', 'start_date', 'end_date')
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }


class SemesterForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Semester'

    class Meta:
        model = Semester
        fields = ('session', 'name', 'registration_start', 'registration_end')
        widgets = {
            'registration_start': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'registration_end': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }


class LevelSemesterStateForm(CrispyFormMixin, forms.Form):
    """Sets (or clears) the current semester for one student level - the
    per-level replacement for the old global "activate semester" action.
    Leaving the semester blank puts the level into a "no semester in
    progress" state.
    """
    submit_label = 'Save'

    level = forms.TypedChoiceField(choices=Level.choices, coerce=int)
    semester = forms.ModelChoiceField(
        queryset=Semester.objects.select_related('session'),
        required=False,
        help_text='Leave blank to mark this level as having no semester in progress.',
    )


class LevelSemesterSelectionForm(forms.Form):
    """Program -> Level -> Semester-Session selector. The semester is
    still stored per level (LevelSemesterState); the programme only
    scopes which levels are valid, so an invalid combination (e.g. 300
    Level for a 2-level certificate) is rejected server-side.
    """
    programme = forms.ModelChoiceField(queryset=Programme.objects.none())
    level = forms.TypedChoiceField(choices=Level.choices, coerce=int)
    semester = forms.ModelChoiceField(queryset=Semester.objects.select_related('session'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programme'].queryset = Programme.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        programme = cleaned.get('programme')
        level = cleaned.get('level')
        if programme and level and level not in programme.levels:
            self.add_error('level', f'{programme} does not have a {dict(Level.choices)[level]}.')
        return cleaned


class RegistrationWindowForm(CrispyFormMixin, forms.Form):
    """Focused form for the "manage a semester's registration deadlines"
    quick action - FR-REG-03 calls this out specifically, separate from
    editing every other field on the semester.
    """
    submit_label = 'Save Registration Window'

    registration_start = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )
    registration_end = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('registration_start')
        end = cleaned_data.get('registration_end')
        if start and end and end <= start:
            self.add_error('registration_end', 'Registration close date must be after the open date.')
        return cleaned_data
