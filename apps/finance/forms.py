from django import forms
from django.db import models

from apps.core.constants import Level
from apps.core.forms import CrispyFormMixin

from .models import FeeStructure, FeeType, Invoice


class FeeTypeForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Fee Type'

    class Meta:
        model = FeeType
        fields = ('name', 'description')


class FeeStructureForm(CrispyFormMixin, forms.ModelForm):
    submit_label = 'Save Fee Structure'

    class Meta:
        model = FeeStructure
        fields = ('fee_type', 'department', 'level', 'session', 'amount', 'description')


class BulkInvoiceGenerateForm(CrispyFormMixin, forms.Form):
    submit_label = 'Generate Invoices'

    fee_structure = forms.ModelChoiceField(
        queryset=FeeStructure.objects.select_related('fee_type', 'department', 'session'),
        label='Fee Structure',
        help_text='Invoices will be generated for every active student in this fee structure\'s department and level.',
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
        queryset=FeeStructure.objects.select_related('fee_type', 'department', 'session'),
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
