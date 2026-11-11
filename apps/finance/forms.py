from django import forms

from apps.core.constants import Level
from apps.core.forms import CrispyFormMixin, DepartmentScopedSelect

from .models import FeeStructure, FeeType, Invoice


class FeeTypeForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Fee Type'

    class Meta:
        model = FeeType
        fields = ('name', 'description')


class FeeStructureForm(CrispyFormMixin, forms.ModelForm):
    """Programme/Semester are optional narrowing fields (both blank
    means "every programme, the whole session") - see FeeStructure's
    docstring for the most-specific-wins resolution this feeds.
    """
    submit_label = 'Save Fee Structure'

    class Meta:
        model = FeeStructure
        fields = (
            'programme', 'department', 'level', 'session', 'semester', 'fee_type',
            'description', 'amount', 'due_date', 'is_published',
        )
        labels = {
            'programme': 'Program',
            'description': 'Invoice title / description',
            'due_date': 'Payment deadline',
            'is_published': 'Published (generate invoices and make visible to eligible students)',
        }
        widgets = {'due_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.academics.models import Semester
        from apps.admissions.models import Programme

        # A Program is required when creating a fee; existing department-wide
        # fees (programme blank) stay valid and keep editing without one.
        editing_department_wide = not self.instance._state.adding and not self.instance.programme_id
        self.fields['programme'].required = not editing_department_wide
        self.fields['programme'].empty_label = 'Select program' if not editing_department_wide else 'Every programme in the department'
        programme_qs = Programme.objects.filter(is_active=True)
        self.fields['programme'].queryset = programme_qs
        self.fields['programme'].widget = DepartmentScopedSelect(
            attrs={'data-scoped-by': 'department'},
            department_by_value={
                str(pk): str(department_id)
                for pk, department_id in programme_qs.values_list('pk', 'department_id')
                if department_id is not None
            },
        )
        self.fields['programme'].widget.choices = self.fields['programme'].choices

        self.fields['semester'].required = False
        self.fields['semester'].empty_label = 'The whole session'
        self.fields['semester'].queryset = Semester.objects.select_related('session')

    def clean(self):
        cleaned_data = super().clean()
        programme = cleaned_data.get('programme')
        level = cleaned_data.get('level')
        semester = cleaned_data.get('semester')
        session = cleaned_data.get('session')
        if programme and level and level not in programme.levels:
            self.add_error('level', f'{programme} does not have a {dict(Level.choices)[level]}.')
        if semester and session and semester.session_id != session.pk:
            self.add_error('semester', 'This semester belongs to a different academic session.')
        return cleaned_data


class BulkInvoiceGenerateForm(CrispyFormMixin, forms.Form):
    submit_label = 'Generate Invoices'

    fee_structure = forms.ModelChoiceField(
        queryset=FeeStructure.objects.filter(is_published=True).select_related(
            'fee_type', 'department', 'programme', 'session', 'semester'),
        label='Fee Structure',
        help_text='Invoices are generated only for eligible students: this fee\'s department, level and '
                  'programme, whose level is currently running the fee\'s session/semester.',
    )
    due_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Leave blank to use the fee structure\'s own payment deadline.',
    )


class BulkInvoiceGenerateAllFeeTypesForm(CrispyFormMixin, forms.Form):
    submit_label = 'Generate Invoices'

    department = forms.ModelChoiceField(queryset=None)
    level = forms.TypedChoiceField(choices=Level.choices, coerce=int)
    session = forms.ModelChoiceField(queryset=None)
    due_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'}),
        help_text='Applied to every invoice generated across all fee types.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.academics.selectors import get_active_sessions
        from apps.departments.selectors import get_active_departments
        self.fields['department'].queryset = get_active_departments()
        self.fields['session'].queryset = get_active_sessions()


class IndividualInvoiceGenerateForm(CrispyFormMixin, forms.Form):
    submit_label = 'Generate Invoice'

    student = forms.ModelChoiceField(
        queryset=None,
        help_text='Search by matric number or name.',
    )
    fee_structure = forms.ModelChoiceField(
        queryset=FeeStructure.objects.filter(is_published=True).select_related(
            'fee_type', 'department', 'programme', 'session', 'semester'),
        label='Fee Structure',
    )
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.students.models import Student
        self.fields['student'].queryset = Student.objects.select_related('user').filter(
            status=Student.Status.ACTIVE,
        )


class RecordOfflinePaymentForm(CrispyFormMixin, forms.Form):
    submit_label = 'Record Payment'

    invoice = forms.ModelChoiceField(
        queryset=None,
        help_text='Only invoices with an outstanding balance are shown.',
    )
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    reference = forms.CharField(
        max_length=100,
        label='Teller / Reference Number',
        help_text='e.g. bank teller number or transaction reference.',
    )
    notes = forms.CharField(max_length=255, required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['invoice'].queryset = Invoice.objects.exclude(
            status=Invoice.Status.PAID,
        ).select_related('student', 'student__user', 'fee_structure')

    def clean(self):
        cleaned_data = super().clean()
        invoice = cleaned_data.get('invoice')
        amount = cleaned_data.get('amount')
        if invoice and amount and amount > invoice.balance:
            self.add_error('amount', f'Exceeds the outstanding balance of {invoice.balance}.')
        return cleaned_data
