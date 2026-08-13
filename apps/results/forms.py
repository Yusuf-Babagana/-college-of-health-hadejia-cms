from django import forms
from django.forms import modelformset_factory

from apps.core.forms import CrispyFormMixin

from .models import Grade, GradeBand


class GradeBandForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Grade Band'

    class Meta:
        model = GradeBand
        fields = ('letter', 'min_score', 'max_score', 'grade_point')


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
