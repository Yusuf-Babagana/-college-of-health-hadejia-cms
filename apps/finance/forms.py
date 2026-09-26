from django import forms
from django.db import models

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
        fields = ('fee_type', 'department', 'programme', 'level', 'session', 'semester', 'amount', 'description')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.academics.models import Semester
        from apps.admissions.models import Programme

        self.fields['programme'].required = False
        self.fields['programme'].empty_label = 'Every programme in the department'
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


class BulkInvoiceGenerateForm(CrispyFormMixin, forms.Form):
    submit_label = 'Generate Invoices'

    fee_structure = forms.ModelChoiceField(
        queryset=FeeStructure.objects.select_related('fee_type', 'department', 'programme', 'session', 'semester'),
        label='Fee Structure',
        help_text='Invoices will be generated for every active student in this fee structure\'s department and level '
                  '(narrowed to its programme too, if it\'s scoped to one).',
    )
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))


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
        queryset=FeeStructure.objects.select_related('fee_type', 'department', 'programme', 'session', 'semester'),
        label='Fee Structure',
    )
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.students.models import Student
        self.fields['student'].queryset = Student.objects.select_related('user').filter(
            status=Student.Status.ACTIVE,
        )


class StudentInvoiceGenerateForm(CrispyFormMixin, forms.Form):
    """FR-FIN: student self-service invoice generation - Programme
    narrows to the student's own department (defaulting to whatever's
    already on their profile), Semester to the session currently
    running for their level (see academics.selectors.get_semester_for_level).
    """
    submit_label = 'Generate Invoice'

    programme = forms.ModelChoiceField(
        queryset=None, required=False,
        help_text='Leave blank if your programme isn\'t listed or doesn\'t affect your fees.',
    )
    semester = forms.ModelChoiceField(queryset=None, empty_label=None)

    def __init__(self, *args, student, **kwargs):
        super().__init__(*args, **kwargs)
        from django.urls import reverse

        from apps.academics.models import Semester
        from apps.academics.selectors import get_semester_for_level
        from apps.admissions.models import Programme

        self.helper.form_action = reverse('finance:generate_my_invoice')

        # Never filter Programme by department= here - Programme.department
        # is NULL on most real rows in this system (see
        # apps.admissions.models.Programme), so that filter would silently
        # empty the dropdown for most students. Show every active
        # programme instead, same as GradeBandForm/FeeStructureForm.
        self.fields['programme'].queryset = Programme.objects.filter(is_active=True)
        if student.programme_id:
            self.fields['programme'].initial = student.programme_id

        current_semester = get_semester_for_level(student.level)
        self.fields['semester'].queryset = (
            Semester.objects.filter(pk=current_semester.pk) if current_semester else Semester.objects.none()
        )
        if current_semester:
            self.fields['semester'].initial = current_semester.pk


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


class InitiateOnlinePaymentForm(CrispyFormMixin, forms.Form):
    """Lets a student choose to pay an invoice's full balance or a
    part payment via Paystack. The amount field is only required (and
    only validated against the balance) when 'partial' is chosen -
    'full' always pays whatever the balance is at submit time.
    """
    submit_label = 'Proceed to Paystack'

    class PaymentType(models.TextChoices):
        FULL = 'full', 'Pay full balance'
        PARTIAL = 'partial', 'Make a part payment'

    payment_type = forms.ChoiceField(
        choices=PaymentType.choices,
        widget=forms.RadioSelect,
        initial=PaymentType.FULL,
        label='How much would you like to pay?',
    )
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        label='Part payment amount',
        help_text='Only needed if you selected "Make a part payment" above.',
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
    )

    def __init__(self, *args, invoice, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        payment_type = cleaned_data.get('payment_type')
        amount = cleaned_data.get('amount')

        if payment_type == self.PaymentType.PARTIAL:
            if amount is None:
                self.add_error('amount', 'Enter the amount you want to pay.')
            elif amount <= 0:
                self.add_error('amount', 'Amount must be greater than zero.')
            elif amount >= self.invoice.balance:
                self.add_error(
                    'amount',
                    f'This is not less than the outstanding balance of {self.invoice.balance}. '
                    'Choose "Pay full balance" instead.',
                )
            else:
                cleaned_data['amount'] = amount
        else:
            cleaned_data['amount'] = self.invoice.balance

        return cleaned_data
