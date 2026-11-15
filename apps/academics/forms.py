from django import forms
from django.core.exceptions import ValidationError

from apps.core.constants import Level
from apps.core.forms import CrispyFormMixin

from apps.admissions.models import Programme

from . import selectors
from .models import AcademicSession, LevelSemesterState, Semester
from .models.level_state import DUPLICATE_MESSAGE


class AcademicSessionForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Session'

    class Meta:
        model = AcademicSession
        fields = ('name', 'start_date', 'end_date', 'programmes')
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'programmes': 'Hold Ctrl/Cmd to pick several. Leave empty if this session applies to every programme.',
        }


class ProgrammeSessionFieldsMixin:
    """Programme -> Academic Session -> Semester for Semester forms (the
    app's own screen and the Django admin share it). The Session choices
    are limited to the posted/saved Programme's sessions, so a session
    that doesn't belong to the programme is rejected by the server as an
    invalid choice - the JavaScript only makes that nicer to use.
    """

    def _setup_programme_session(self):
        from django.urls import reverse

        programme_field = self.fields['programme']
        programme_field.required = True
        programme_field.queryset = Programme.objects.filter(is_active=True)
        programme_field.empty_label = '--------- Select a programme first ---------'
        programme_field.widget.attrs['data-sessions-url'] = reverse('academics:semester_session_options')
        programme_field.widget.attrs['data-session-target'] = 'session'

        raw = self.data.get(self.add_prefix('programme')) if self.is_bound else self.instance.programme_id
        programme = None
        if raw:
            try:
                programme = Programme.objects.filter(pk=raw).first()
            except (ValueError, ValidationError):
                programme = None

        session_field = self.fields['session']
        session_field.queryset = selectors.get_sessions_for_programme(programme)
        session_field.empty_label = '--------- Select a session ---------'
        if programme is None:
            session_field.widget.attrs['disabled'] = True  # until a programme is chosen

    def clean(self):
        cleaned = super().clean()
        programme, session = cleaned.get('programme'), cleaned.get('session')
        if programme and session and not session.applies_to(programme):
            self.add_error('session', f'{session} is not an academic session for {programme}.')
        return cleaned

    class Media:
        js = ('js/programme-session-select.js',)


class SemesterForm(ProgrammeSessionFieldsMixin, CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Semester'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_programme_session()

    class Meta:
        model = Semester
        fields = ('programme', 'session', 'name', 'registration_start', 'registration_end')
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
        queryset=Semester.objects.select_related('session', 'programme'),
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
    semester = forms.ModelChoiceField(queryset=Semester.objects.select_related('session', 'programme'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programme'].queryset = Programme.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        programme = cleaned.get('programme')
        level = cleaned.get('level')
        semester = cleaned.get('semester')
        if programme and level and level not in programme.levels:
            self.add_error('level', f'{programme} does not have a {dict(Level.choices)[level]}.')
        elif programme and semester and semester.programme_id and semester.programme_id != programme.pk:
            self.add_error('semester', f'{semester} belongs to a different programme than {programme}.')
        elif programme and level and semester and LevelSemesterState.objects.filter(
            programme=programme, level=level, semester=semester,
        ).exists():
            self.add_error('semester', DUPLICATE_MESSAGE)
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
