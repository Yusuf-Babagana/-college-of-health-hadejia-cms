import csv
import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, FormView, ListView, UpdateView, View

from apps.academics.selectors import get_active_sessions
from apps.core.constants import Level, Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin
from apps.departments.selectors import get_active_departments

from . import paystack, selectors, services
from .forms import (
    BulkInvoiceGenerateAllFeeTypesForm,
    BulkInvoiceGenerateForm,
    FeeStructureForm,
    FeeTypeForm,
    IndividualInvoiceGenerateForm,
    InitiateOnlinePaymentForm,
    RecordOfflinePaymentForm,
)
from .models import FeeStructure, FeeType, Invoice, Payment

logger = logging.getLogger('apps')


class FinanceManagementRoleMixin(RoleRequiredMixin):
    """FR-FIN-01: fee structure management is the Bursar's job."""
    allowed_roles = (Role.BURSAR, Role.SUPER_ADMIN)


class FeeTypeListView(FinanceManagementRoleMixin, PaginatedListMixin, ListView):
    """Bursar manages the different activities the school collects money
    for (Tuition, Registration, Practical, Board Exams, etc.), each of
    which gets billed and invoiced separately.
    """
    template_name = 'finance/fee_type_list.html'
    context_object_name = 'fee_types'

    def get_queryset(self):
        return selectors.get_fee_type_list(
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class FeeTypeCreateView(FinanceManagementRoleMixin, CreateView):
    model = FeeType
    form_class = FeeTypeForm
    template_name = 'finance/fee_type_form.html'
    success_url = reverse_lazy('finance:fee_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Fee Type'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Fee type "{form.instance}" created.')
        return super().form_valid(form)


class FeeTypeUpdateView(FinanceManagementRoleMixin, UpdateView):
    model = FeeType
    form_class = FeeTypeForm
    template_name = 'finance/fee_type_form.html'
    success_url = reverse_lazy('finance:fee_type_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Fee type "{form.instance}" updated.')
        return super().form_valid(form)


class FeeTypeArchiveToggleView(FinanceManagementRoleMixin, View):
    def post(self, request, pk):
        fee_type = get_object_or_404(FeeType.all_objects, pk=pk)
        if fee_type.is_deleted:
            services.restore_fee_type(fee_type)
            messages.success(request, f'Fee type "{fee_type}" restored.')
        else:
            services.archive_fee_type(fee_type)
            messages.success(request, f'Fee type "{fee_type}" archived.')
        return redirect('finance:fee_type_list')


class FeeStructureListView(FinanceManagementRoleMixin, PaginatedListMixin, ListView):
    template_name = 'finance/fee_structure_list.html'
    context_object_name = 'fee_structures'

    def get_queryset(self):
        return selectors.get_fee_structure_list(
            session=self.request.GET.get('session'),
            department=self.request.GET.get('department'),
            level=self.request.GET.get('level'),
            fee_type=self.request.GET.get('fee_type'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = get_active_sessions()
        context['departments'] = get_active_departments()
        context['fee_types'] = selectors.get_active_fee_types()
        context['level_choices'] = Level.choices
        context['current_session'] = self.request.GET.get('session', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_level'] = self.request.GET.get('level', '')
        context['current_fee_type'] = self.request.GET.get('fee_type', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class FeeStructureCreateView(FinanceManagementRoleMixin, CreateView):
    model = FeeStructure
    form_class = FeeStructureForm
    template_name = 'finance/fee_structure_form.html'
    success_url = reverse_lazy('finance:fee_structure_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Add Fee Structure'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Fee structure "{form.instance}" created.')
        return super().form_valid(form)


class FeeStructureUpdateView(FinanceManagementRoleMixin, UpdateView):
    model = FeeStructure
    form_class = FeeStructureForm
    template_name = 'finance/fee_structure_form.html'
    success_url = reverse_lazy('finance:fee_structure_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Edit {self.object}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Fee structure "{form.instance}" updated.')
        return super().form_valid(form)


class FeeStructureArchiveToggleView(FinanceManagementRoleMixin, View):
    def post(self, request, pk):
        fee_structure = get_object_or_404(FeeStructure.all_objects, pk=pk)
        if fee_structure.is_deleted:
            services.restore_fee_structure(fee_structure)
            messages.success(request, f'Fee structure "{fee_structure}" restored.')
        else:
            services.archive_fee_structure(fee_structure)
            messages.success(request, f'Fee structure "{fee_structure}" archived.')
        return redirect('finance:fee_structure_list')


class InvoiceListView(FinanceManagementRoleMixin, PaginatedListMixin, ListView):
    """FR-FIN-03 (partial): view all generated invoices and their status."""
    template_name = 'finance/invoice_list.html'
    context_object_name = 'invoices'

    def get_queryset(self):
        return selectors.get_invoice_list(
            session=self.request.GET.get('session'),
            department=self.request.GET.get('department'),
            level=self.request.GET.get('level'),
            status=self.request.GET.get('status'),
            fee_type=self.request.GET.get('fee_type'),
            include_archived=self.request.GET.get('archived') == '1',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = get_active_sessions()
        context['departments'] = get_active_departments()
        context['fee_types'] = selectors.get_active_fee_types()
        context['level_choices'] = Level.choices
        context['status_choices'] = Invoice.Status.choices
        context['current_session'] = self.request.GET.get('session', '')
        context['current_department'] = self.request.GET.get('department', '')
        context['current_level'] = self.request.GET.get('level', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['current_fee_type'] = self.request.GET.get('fee_type', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'
        return context


class BulkInvoiceGenerateView(FinanceManagementRoleMixin, FormView):
    """FR-FIN-02: bulk generation for a whole department/level."""
    form_class = BulkInvoiceGenerateForm
    template_name = 'finance/invoice_generate_bulk.html'
    success_url = reverse_lazy('finance:invoice_list')

    def form_valid(self, form):
        created_count, skipped_count = services.bulk_generate_invoices(
            fee_structure=form.cleaned_data['fee_structure'],
            due_date=form.cleaned_data['due_date'],
        )
        if created_count:
            messages.success(
                self.request,
                f'Generated {created_count} invoice(s). '
                f'{skipped_count} student(s) already had an invoice for this fee structure and were skipped.'
                if skipped_count else f'Generated {created_count} invoice(s).',
            )
        else:
            messages.warning(
                self.request,
                'No invoices were generated - every matching active student already has one for this fee structure.',
            )
        return redirect(self.success_url)


class BulkInvoiceGenerateAllFeeTypesView(FinanceManagementRoleMixin, FormView):
    """Generates invoices for every fee type billed to a department/level/
    session in one action (Tuition, Registration, Practical, Board Exams,
    etc.), instead of the Bursar running the single-fee-type bulk
    generator once per activity every session.
    """
    form_class = BulkInvoiceGenerateAllFeeTypesForm
    template_name = 'finance/invoice_generate_bulk_all.html'
    success_url = reverse_lazy('finance:invoice_list')

    def form_valid(self, form):
        try:
            breakdown = services.bulk_generate_invoices_for_all_fee_types(
                department=form.cleaned_data['department'],
                level=form.cleaned_data['level'],
                session=form.cleaned_data['session'],
                due_date=form.cleaned_data['due_date'],
            )
        except ValidationError as exc:
            form.add_error(None, exc.message)
            return self.form_invalid(form)

        total_created = sum(row['created'] for row in breakdown)
        total_skipped = sum(row['skipped'] for row in breakdown)

        if total_created:
            parts = ', '.join(f"{row['fee_type']}: {row['created']}" for row in breakdown if row['created'])
            message = f'Generated {total_created} invoice(s) across {len(breakdown)} fee type(s) ({parts}).'
            if total_skipped:
                message += f' {total_skipped} already-billed invoice(s) skipped.'
            messages.success(self.request, message)
        else:
            messages.warning(
                self.request,
                'No invoices were generated - every matching active student already has an invoice '
                'for every fee type in this department, level, and session.',
            )
        return redirect(self.success_url)


class IndividualInvoiceGenerateView(FinanceManagementRoleMixin, FormView):
    """FR-FIN-02: individual generation for a single student."""
    form_class = IndividualInvoiceGenerateForm
    template_name = 'finance/invoice_generate_individual.html'
    success_url = reverse_lazy('finance:invoice_list')

    def form_valid(self, form):
        try:
            invoice = services.generate_invoice(
                student=form.cleaned_data['student'],
                fee_structure=form.cleaned_data['fee_structure'],
                due_date=form.cleaned_data['due_date'],
            )
        except ValidationError as exc:
            form.add_error(None, exc.message)
            return self.form_invalid(form)

        messages.success(self.request, f'Invoice generated for {invoice.student.matric_number}.')
        return redirect(self.success_url)


class MyInvoicesView(RoleRequiredMixin, ListView):
    """FR-FIN-04 (student-facing half): a student's own invoices, so they
    can actually see what they owe and pay it.
    """
    allowed_roles = (Role.STUDENT,)
    template_name = 'finance/my_invoices.html'
    context_object_name = 'invoices'

    def get_queryset(self):
        student_profile = getattr(self.request.user, 'student_profile', None)
        if not student_profile:
            return Invoice.objects.none()
        return selectors.get_invoices_for_student(student_profile)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['student_profile'] = getattr(self.request.user, 'student_profile', None)
        return context


class PaymentListView(FinanceManagementRoleMixin, PaginatedListMixin, ListView):
    """FR-FIN-03: view all payments and their statuses."""
    template_name = 'finance/payment_list.html'
    context_object_name = 'payments'

    def get_queryset(self):
        qs = Payment.objects.select_related(
            'invoice', 'invoice__student', 'invoice__student__user', 'verified_by',
        )
        method = self.request.GET.get('method')
        status = self.request.GET.get('status')
        if method:
            qs = qs.filter(method=method)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['method_choices'] = Payment.Method.choices
        context['status_choices'] = Payment.Status.choices
        context['current_method'] = self.request.GET.get('method', '')
        context['current_status'] = self.request.GET.get('status', '')
        return context


class RecordOfflinePaymentView(FinanceManagementRoleMixin, FormView):
    """FR-FIN-03: Bursar manually records a bank-teller payment."""
    form_class = RecordOfflinePaymentForm
    template_name = 'finance/record_offline_payment.html'
    success_url = reverse_lazy('finance:invoice_list')

    def form_valid(self, form):
        try:
            payment = services.record_offline_payment(
                invoice=form.cleaned_data['invoice'],
                amount=form.cleaned_data['amount'],
                reference=form.cleaned_data['reference'],
                notes=form.cleaned_data['notes'],
                recorded_by=self.request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc.message)
            return self.form_invalid(form)

        messages.success(
            self.request,
            f'Payment of {payment.amount} recorded for {payment.invoice.student.matric_number}. '
            f'Invoice status: {payment.invoice.get_status_display()}.',
        )
        return redirect(self.success_url)


class VerifyOnlinePaymentView(FinanceManagementRoleMixin, View):
    """FR-FIN-03: manual fallback to re-check a pending online payment
    against Paystack directly, in case the browser callback or webhook
    never fired.
    """
    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, method=Payment.Method.ONLINE)
        try:
            services.verify_online_payment(payment.reference)
        except (ValidationError, paystack.PaystackError) as exc:
            messages.error(request, str(exc))
        else:
            payment.refresh_from_db()
            messages.success(request, f'Payment {payment.reference} is now {payment.get_status_display()}.')
        return redirect('finance:payment_list')


class InitiateOnlinePaymentView(RoleRequiredMixin, View):
    """Student picks full balance vs. a part payment, then is redirected
    to Paystack's hosted checkout for that amount. GET shows the choice;
    POST processes it - this can't be a plain FormView because the form
    itself needs the invoice (to validate the amount against its balance)
    before it can be built.
    """
    allowed_roles = (Role.STUDENT,)
    template_name = 'finance/initiate_payment.html'

    def get_invoice(self, request, pk):
        student_profile = getattr(request.user, 'student_profile', None)
        if not student_profile:
            return None
        return Invoice.objects.filter(pk=pk, student=student_profile).select_related(
            'fee_structure', 'fee_structure__fee_type', 'fee_structure__session',
        ).first()

    def get(self, request, pk):
        invoice = self.get_invoice(request, pk)
        if not invoice:
            messages.error(request, 'Invoice not found.')
            return redirect('finance:my_invoices')
        if invoice.balance <= 0:
            messages.info(request, 'This invoice has no outstanding balance.')
            return redirect('finance:my_invoices')

        form = InitiateOnlinePaymentForm(invoice=invoice)
        return render(request, self.template_name, {'form': form, 'invoice': invoice})

    def post(self, request, pk):
        invoice = self.get_invoice(request, pk)
        if not invoice:
            messages.error(request, 'Invoice not found.')
            return redirect('finance:my_invoices')

        form = InitiateOnlinePaymentForm(request.POST, invoice=invoice)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'invoice': invoice})

        callback_url = request.build_absolute_uri(reverse('finance:payment_callback'))
        try:
            authorization_url = services.initiate_online_payment(
                invoice=invoice,
                email=request.user.email,
                callback_url=callback_url,
                amount=form.cleaned_data['amount'],
            )
        except (ValidationError, paystack.PaystackError) as exc:
            form.add_error(None, str(exc))
            return render(request, self.template_name, {'form': form, 'invoice': invoice})

        return redirect(authorization_url)


class PaymentCallbackView(LoginRequiredMixin, View):
    """Paystack redirects the payer's browser here after checkout."""

    def get(self, request):
        reference = request.GET.get('reference')
        if not reference:
            messages.error(request, 'Missing payment reference.')
            return redirect('finance:my_invoices')

        try:
            payment = services.verify_online_payment(reference)
        except (ValidationError, paystack.PaystackError) as exc:
            messages.error(request, str(exc))
            return redirect('finance:my_invoices')

        if payment.status == Payment.Status.SUCCESSFUL:
            messages.success(request, f'Payment successful! Invoice status: {payment.invoice.get_status_display()}.')
        else:
            messages.error(request, 'Payment was not successful. Please try again.')
        return redirect('finance:my_invoices')


@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(View):
    """Server-to-server notification from Paystack - the reliable path,
    independent of whether the payer's browser makes it back to the
    callback view. No login/CSRF: this is Paystack's server calling us,
    not a browser session.
    """

    def post(self, request):
        if not paystack.verify_webhook_signature(request):
            logger.warning('Rejected Paystack webhook with invalid signature')
            return HttpResponseBadRequest('Invalid signature')

        event = json.loads(request.body)

        if event.get('event') == 'charge.success':
            reference = event['data']['reference']
            try:
                services.verify_online_payment(reference)
            except (ValidationError, paystack.PaystackError):
                logger.exception('Failed to process Paystack webhook for reference %s', reference)

        return HttpResponse(status=200)


class DefaulterListView(FinanceManagementRoleMixin, PaginatedListMixin, ListView):
    """FR-FIN-05: students with an outstanding balance past their due date."""
    template_name = 'finance/defaulter_list.html'
    context_object_name = 'defaulters'

    def get_queryset(self):
        return selectors.get_defaulters(
            session=self.request.GET.get('session'),
            department=self.request.GET.get('department'),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = get_active_sessions()
        context['departments'] = get_active_departments()
        context['current_session'] = self.request.GET.get('session', '')
        context['current_department'] = self.request.GET.get('department', '')
        return context


class DefaulterExportView(FinanceManagementRoleMixin, View):
    """FR-FIN-05: export the same defaulter list as CSV."""

    def get(self, request):
        defaulters = selectors.get_defaulters(
            session=request.GET.get('session'),
            department=request.GET.get('department'),
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="defaulters.csv"'

        writer = csv.writer(response)
        writer.writerow(['Matric Number', 'Name', 'Department', 'Fee Structure', 'Amount Due', 'Amount Paid', 'Balance', 'Due Date'])
        for invoice in defaulters:
            writer.writerow([
                invoice.student.matric_number,
                invoice.student.user.get_full_name(),
                invoice.student.department.code,
                str(invoice.fee_structure),
                invoice.amount_due,
                invoice.amount_paid,
                invoice.balance,
                invoice.due_date,
            ])
        return response
