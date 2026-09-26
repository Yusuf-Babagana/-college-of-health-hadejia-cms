from django import forms

from apps.core.forms import CrispyFormMixin, DepartmentScopedSelect

from .models import Course, CourseOffering


class CourseForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Course'

    class Meta:
        model = Course
        fields = (
            'code', 'title', 'credit_units', 'level', 'semester_name', 'department', 'programme',
            'eligible_departments', 'eligible_programmes',
        )
        widgets = {
            'eligible_departments': forms.CheckboxSelectMultiple(),
            'eligible_programmes': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        programme_field = self.fields['programme']
        programme_field.queryset = programme_field.queryset.filter(is_active=True)
        programme_field.required = False
        programme_field.help_text = 'Choose the Department above first - Programme narrows to match it.'
        programme_field.widget = DepartmentScopedSelect(
            attrs={'data-scoped-by': 'department'},
            department_by_value={
                str(pk): str(department_id)
                for pk, department_id in programme_field.queryset.values_list('pk', 'department_id')
                if department_id is not None
            },
        )
        programme_field.widget.choices = programme_field.choices

        self.fields['eligible_departments'].required = False
        self.fields['eligible_programmes'].required = False
        self.fields['eligible_programmes'].queryset = self.fields['eligible_programmes'].queryset.filter(
            is_active=True,
        )


class CourseOfferingForm(CrispyFormMixin, forms.ModelForm):
    """HOD-facing: course choices are scoped to the HOD's own department,
    passed in from the view - a course genuinely belongs to one
    department. The lecturer choice is deliberately NOT department-
    scoped: a lecturer's Lecturer.department is just their one home
    profile/login, but the same lecturer can be assigned to teach a
    course in any department (one login, no separate account per
    department taught) - see FR-LEC-01. Lecturer.__str__ appends the
    lecturer's home department code, so the dropdown still shows where
    each one is normally based.

    The semester is never a free user choice - FR-HOD-02 activates a
    course for the semester its LEVEL is currently running (per
    LevelSemesterState), resolved in clean() from the selected course.
    Keeping semester as a real (if hidden) ModelChoiceField - rather than
    dropping it from the form entirely - matters: Django's full_clean()
    only enforces the unique_offering_per_course_semester constraint for
    fields that are actually part of the form.
    """
    submit_label = 'Save Course Offering'

    class Meta:
        model = CourseOffering
        fields = ('course', 'semester', 'lecturer', 'capacity')
        widgets = {'semester': forms.HiddenInput()}

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.lecturers.models import Lecturer

        if department is not None:
            self.fields['course'].queryset = Course.objects.filter(department=department)
        self.fields['lecturer'].queryset = Lecturer.objects.select_related('user', 'department').order_by(
            'user__first_name', 'user__last_name',
        )
        self.fields['lecturer'].required = False
        self.fields['lecturer'].help_text = (
            'Any lecturer college-wide can be assigned - not just this department\'s own staff, '
            'since one lecturer can teach courses in several departments under a single login.'
        )
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
            elif semester.name != course.semester_name:
                self.add_error(
                    'course',
                    f'"{course.code}" is a {course.get_semester_name_display()} course, but '
                    f'{course.get_level_display()} is currently running {semester.get_name_display()}.',
                )
            cleaned_data['semester'] = semester

        return cleaned_data
