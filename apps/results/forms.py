from django import forms
from django.forms import modelformset_factory

from apps.core.forms import CrispyFormMixin, DepartmentScopedSelect

from .models import Grade, GradeBand


class GradeBandForm(CrispyFormMixin, forms.ModelForm):
    """Department/Programme choose the SCOPE this band applies to (both
    optional - blank/blank means the college-wide default); Programme is
    scoped to whichever Department is picked via the same
    DepartmentScopedSelect widget the Course/Student forms use, though
    since Programme.department is unreliable in this system's real data,
    that's a UI convenience only - the two fields are stored and
    validated independently (see GradeBand.clean).
    """
    submit_label = 'Save Grade Band'

    class Meta:
        model = GradeBand
        fields = ('department', 'programme', 'letter', 'min_score', 'max_score', 'grade_point')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.admissions.models import Programme
        from apps.departments.selectors import get_active_departments

        self.fields['department'].queryset = get_active_departments()
        self.fields['department'].required = False
        self.fields['department'].empty_label = 'College-wide (all departments)'

        programme_qs = Programme.objects.filter(is_active=True)
        self.fields['programme'].queryset = programme_qs
        self.fields['programme'].required = False
        self.fields['programme'].empty_label = 'Every programme in the department'
        self.fields['programme'].help_text = 'Choose the Department above first.'
        self.fields['programme'].widget = DepartmentScopedSelect(
            attrs={'data-scoped-by': 'department'},
            department_by_value={
                str(pk): str(department_id)
                for pk, department_id in programme_qs.values_list('pk', 'department_id')
                if department_id is not None
            },
        )
        self.fields['programme'].widget.choices = self.fields['programme'].choices


# Bulk grade entry: one row per student, editable only for grades still
# in Draft/Rejected status - the queryset passed in the view already
# excludes locked grades, so there's no need to disable fields here.
# x-model bindings let the template live-recalculate the total (FR-LEC-03)
# without a page reload - each row is its own Alpine scope, so the same
# variable names ("ca"/"exam") are safe to reuse across every row.
GradeEntryFormSet = modelformset_factory(
    Grade,
    fields=('ca1_score', 'ca2_score', 'exam_score'),
    extra=0,
    widgets={
        'ca1_score': forms.NumberInput(attrs={
            'class': 'form-control form-control-sm', 'step': '0.5', 'x-model.number': 'ca1',
        }),
        'ca2_score': forms.NumberInput(attrs={
            'class': 'form-control form-control-sm', 'step': '0.5', 'x-model.number': 'ca2',
        }),
        'exam_score': forms.NumberInput(attrs={
            'class': 'form-control form-control-sm', 'step': '0.5', 'x-model.number': 'exam',
        }),
    },
)
