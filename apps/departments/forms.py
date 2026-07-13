from django import forms

from apps.core.forms import CrispyFormMixin

from .models import Department


class DepartmentForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Department'

    class Meta:
        model = Department
        fields = ('name', 'code', 'description')


class AssignHODForm(CrispyFormMixin, forms.Form):
    submit_label = 'Assign HOD'

    lecturer = forms.ModelChoiceField(queryset=None, label='Head of Department', required=False)

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .selectors import get_eligible_hod_choices

        self.department = department
        self.fields['lecturer'].queryset = get_eligible_hod_choices(department)
        self.fields['lecturer'].required = False
        self.fields['lecturer'].help_text = (
            'Only lecturers already assigned to this department can be Head of Department. '
            'Leave blank to remove the current HOD.'
        )
        if department.hod_id:
            self.fields['lecturer'].initial = department.hod_id
