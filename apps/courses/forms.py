from django import forms

from apps.core.forms import CrispyFormMixin

from .models import Course, CourseOffering


class CourseForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Course'

    class Meta:
        model = Course
        fields = ('code', 'title', 'credit_units', 'level', 'department')


class CourseOfferingForm(CrispyFormMixin, forms.ModelForm):
    """HOD-facing: course and lecturer choices are scoped to the HOD's
    own department, passed in from the view. The semester is never a
    free user choice - FR-HOD-02 activates a course for the semester its
    LEVEL is currently running (per LevelSemesterState), resolved in
    clean() from the selected course. Keeping semester as a real (if
    hidden) ModelChoiceField - rather than dropping it from the form
    entirely - matters: Django's full_clean() only enforces the
    unique_offering_per_course_semester constraint for fields that are
    actually part of the form.
    """
    submit_label = 'Save Course Offering'

    class Meta:
        model = CourseOffering
        fields = ('course', 'semester', 'lecturer', 'capacity')
        widgets = {'semester': forms.HiddenInput()}

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if department is not None:
            from apps.lecturers.models import Lecturer

            self.fields['course'].queryset = Course.objects.filter(department=department)
            self.fields['lecturer'].queryset = Lecturer.objects.filter(department=department).select_related('user')
        self.fields['lecturer'].required = False
        self.fields['semester'].required = False
        self.fields['course'].help_text = (
            'The offering goes into the semester currently running for the course\'s level.'
        )

    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get('course')

        # instance.pk is truthy even for unsaved rows (UUIDModel assigns
        # the pk default at instantiation), so check _state.adding.
        if not self.instance._state.adding:
            # Editing never moves an offering to another semester, even if
            # the level has since advanced - grades/registrations hang off it.
            cleaned_data['semester'] = self.instance.semester
        elif course:
            from apps.academics.selectors import get_semester_for_level

            semester = get_semester_for_level(course.level)
            if semester is None:
                self.add_error(
                    'course',
                    f'No semester is in progress for {course.get_level_display()}. '
                    'Ask the Registrar to set one under Level Semesters.',
                )
            cleaned_data['semester'] = semester

        return cleaned_data
