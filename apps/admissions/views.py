import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.core.constants import Role
from apps.core.utils.pdf import render_to_pdf_response

from apps.finance import paystack

from . import services
from .forms import (
    ApplicantLoginForm,
    ApplicantSignupForm,
    ReferralCodeForm,
    SchoolAttendedFormSet,
    SectionAForm,
    SectionDForm,
    SectionEForm,
    SSCESittingForm,
    SSCESubjectResultFormSet,
    UploadedDocumentFormSet,
)
from .mixins import ApplicantRequiredMixin, PaymentRequiredMixin
from .models import Applicant, Application, Programme, ReferralCode, SSCESitting

logger = logging.getLogger('apps')

NEXT_SECTION_URL = {
    'a': 'admissions:section_b',
    'b': 'admissions:section_c',
    'c': 'admissions:section_d',
    'd': 'admissions:section_e',
    'e': 'admissions:summary',
}


def _generate_unique_username(email):
    base = slugify(email.split('@')[0]) or 'applicant'
    username = base
    suffix = 0
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f'{base}{suffix}'
    return username


class HomeView(TemplateView):
    template_name = 'admissions/home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == Role.APPLICANT:
            return redirect('admissions:dashboard')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['programmes'] = Programme.objects.filter(is_active=True)
        return context


class SignupView(View):
    template_name = 'admissions/signup.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('admissions:dashboard')
        return render(request, self.template_name, {'form': ApplicantSignupForm()})

    def post(self, request):
        form = ApplicantSignupForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        data = form.cleaned_data
        username = _generate_unique_username(data['email'])

        user = User.objects.create_user(
            username=username,
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            phone_number=data['phone_number'],
            role=Role.APPLICANT,
            password=data['password1'],
        )
        applicant = Applicant.objects.create(user=user)
        Application.objects.create(applicant=applicant)

        authenticated_user = authenticate(request, username=username, password=data['password1'])
        login(request, authenticated_user)
        messages.success(request, 'Account created! Next, pay the application fee or enter a referral code.')
        return redirect('admissions:dashboard')


class LoginView(View):
    template_name = 'admissions/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('admissions:dashboard')
        return render(request, self.template_name, {'form': ApplicantLoginForm()})

    def post(self, request):
        form = ApplicantLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        email = form.cleaned_data['email']
        password = form.cleaned_data['password']

        user_obj = User.objects.filter(email__iexact=email).first()
        if not user_obj or user_obj.role != Role.APPLICANT:
            form.add_error(None, 'Invalid email or password.')
            return render(request, self.template_name, {'form': form})

        user = authenticate(request, username=user_obj.username, password=password)
        if user is None:
            form.add_error(None, 'Invalid email or password.')
            return render(request, self.template_name, {'form': form})

        login(request, user)
        return redirect('admissions:dashboard')


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect('admissions:home')


class DashboardView(ApplicantRequiredMixin, TemplateView):
    template_name = 'admissions/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['applicant'] = self.applicant
        context['application'] = self.application
        context['fee'] = settings.ADMISSIONS_APPLICATION_FEE
        context['sections'] = [
            ('A: Personal & Guardian Details', 'admissions:section_a', self.application.section_a_complete),
            ('B: Educational History', 'admissions:section_b', self.application.section_b_complete),
            ('C: SSCE Results', 'admissions:section_c', self.application.section_c_complete),
            ('D: Course Selection', 'admissions:section_d', self.application.section_d_complete),
            ('E: Declaration & Documents', 'admissions:section_e', self.application.section_e_complete),
        ]
        return context


class ReferralCodeView(ApplicantRequiredMixin, View):
    template_name = 'admissions/referral_check.html'

    def get(self, request):
        if self.applicant.has_paid:
            return redirect('admissions:dashboard')
        return render(request, self.template_name, {'form': ReferralCodeForm()})

    def post(self, request):
        if self.applicant.has_paid:
            return redirect('admissions:dashboard')

        form = ReferralCodeForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        code_str = form.cleaned_data['code'].strip().upper()
        code_obj = ReferralCode.objects.filter(code=code_str).first()

        if not code_obj:
            form.add_error('code', 'Invalid referral code.')
        elif code_obj.is_used:
            form.add_error('code', 'This referral code has already been used.')
        else:
            code_obj.used_by = self.applicant
            code_obj.used_at = timezone.now()
            code_obj.save(update_fields=['used_by', 'used_at', 'updated_at'])

            self.applicant.has_paid = True
            self.applicant.payment_verified_at = timezone.now()
            self.applicant.referral_code_used = code_obj
            self.applicant.save(update_fields=[
                'has_paid', 'payment_verified_at', 'referral_code_used', 'updated_at',
            ])
            messages.success(request, 'Referral code accepted! You may now complete your application.')
            return redirect('admissions:dashboard')

        return render(request, self.template_name, {'form': form})


class InitiateAdmissionPaymentView(ApplicantRequiredMixin, View):
    template_name = 'admissions/payment.html'

    def get(self, request):
        if self.applicant.has_paid:
            return redirect('admissions:dashboard')
        return render(request, self.template_name, {'fee': settings.ADMISSIONS_APPLICATION_FEE})

    def post(self, request):
        if self.applicant.has_paid:
            return redirect('admissions:dashboard')

        callback_url = request.build_absolute_uri(reverse('admissions:payment_callback'))
        try:
            authorization_url = services.initiate_admission_payment(
                applicant=self.applicant,
                email=request.user.email,
                callback_url=callback_url,
            )
        except paystack.PaystackError as exc:
            messages.error(request, str(exc))
            return redirect('admissions:initiate_payment')

        return redirect(authorization_url)


class AdmissionPaymentCallbackView(ApplicantRequiredMixin, View):
    def get(self, request):
        reference = request.GET.get('reference')
        if not reference:
            messages.error(request, 'Missing payment reference.')
            return redirect('admissions:dashboard')

        try:
            payment = services.verify_admission_payment(reference)
        except (ValidationError, paystack.PaystackError) as exc:
            messages.error(request, str(exc))
            return redirect('admissions:dashboard')

        if payment.status == payment.Status.SUCCESSFUL:
            messages.success(request, 'Payment successful! You may now complete your application.')
        else:
            messages.error(request, 'Payment was not successful. Please try again.')
        return redirect('admissions:dashboard')


@method_decorator(csrf_exempt, name='dispatch')
class AdmissionPaystackWebhookView(View):
    """Server-to-server notification from Paystack - no login/CSRF, since
    this is Paystack's server calling us, not a browser session.
    """

    def post(self, request):
        if not paystack.verify_webhook_signature(request):
            logger.warning('Rejected Paystack webhook with invalid signature (admissions)')
            return HttpResponseBadRequest('Invalid signature')

        event = json.loads(request.body)

        if event.get('event') == 'charge.success':
            reference = event['data']['reference']
            try:
                services.verify_admission_payment(reference)
            except (ValidationError, paystack.PaystackError):
                logger.exception('Failed to process Paystack webhook for reference %s (admissions)', reference)

        return HttpResponse(status=200)


class SectionAView(PaymentRequiredMixin, View):
    template_name = 'admissions/section_a.html'

    def get(self, request):
        form = SectionAForm(instance=self.application)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = SectionAForm(request.POST, instance=self.application)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        form.save()
        self.application.section_a_complete = True
        self.application.save(update_fields=['section_a_complete', 'updated_at'])
        return redirect(NEXT_SECTION_URL['a'])


class SectionBView(PaymentRequiredMixin, View):
    template_name = 'admissions/section_b.html'

    def get(self, request):
        formset = SchoolAttendedFormSet(instance=self.application)
        return render(request, self.template_name, {'formset': formset})

    def post(self, request):
        formset = SchoolAttendedFormSet(request.POST, instance=self.application)
        if not formset.is_valid():
            return render(request, self.template_name, {'formset': formset})

        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for idx, instance in enumerate(instances, start=1):
            instance.application = self.application
            if not instance.order:
                instance.order = idx
            instance.save()

        self.application.section_b_complete = True
        self.application.save(update_fields=['section_b_complete', 'updated_at'])
        return redirect(NEXT_SECTION_URL['b'])


class SectionCView(PaymentRequiredMixin, View):
    template_name = 'admissions/section_c.html'

    def _get_sittings(self):
        sitting1, _ = SSCESitting.objects.get_or_create(application=self.application, sitting_number=1)
        sitting2, _ = SSCESitting.objects.get_or_create(application=self.application, sitting_number=2)
        return sitting1, sitting2

    def get(self, request):
        sitting1, sitting2 = self._get_sittings()
        sittings = [
            (SSCESittingForm(instance=sitting1, prefix='sitting1'),
             SSCESubjectResultFormSet(instance=sitting1, prefix='subjects1')),
            (SSCESittingForm(instance=sitting2, prefix='sitting2'),
             SSCESubjectResultFormSet(instance=sitting2, prefix='subjects2')),
        ]
        return render(request, self.template_name, {'sittings': sittings})

    def post(self, request):
        sitting1, sitting2 = self._get_sittings()
        form1 = SSCESittingForm(request.POST, instance=sitting1, prefix='sitting1')
        form2 = SSCESittingForm(request.POST, instance=sitting2, prefix='sitting2')
        subjects1 = SSCESubjectResultFormSet(request.POST, instance=sitting1, prefix='subjects1')
        subjects2 = SSCESubjectResultFormSet(request.POST, instance=sitting2, prefix='subjects2')

        if not (form1.is_valid() and form2.is_valid() and subjects1.is_valid() and subjects2.is_valid()):
            sittings = [(form1, subjects1), (form2, subjects2)]
            return render(request, self.template_name, {'sittings': sittings})

        form1.save()
        form2.save()
        subjects1.save()
        subjects2.save()

        self.application.section_c_complete = True
        self.application.save(update_fields=['section_c_complete', 'updated_at'])
        return redirect(NEXT_SECTION_URL['c'])


class SectionDView(PaymentRequiredMixin, View):
    template_name = 'admissions/section_d.html'

    def get(self, request):
        form = SectionDForm(instance=self.application)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = SectionDForm(request.POST, instance=self.application)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        form.save()
        self.application.section_d_complete = True
        self.application.save(update_fields=['section_d_complete', 'updated_at'])
        return redirect(NEXT_SECTION_URL['d'])


class SectionEView(PaymentRequiredMixin, View):
    template_name = 'admissions/section_e.html'

    def get(self, request):
        context = {
            'form': SectionEForm(instance=self.application),
            'documents_formset': UploadedDocumentFormSet(instance=self.application),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = SectionEForm(request.POST, request.FILES, instance=self.application)
        documents_formset = UploadedDocumentFormSet(request.POST, request.FILES, instance=self.application)

        if not (form.is_valid() and documents_formset.is_valid()):
            context = {'form': form, 'documents_formset': documents_formset}
            return render(request, self.template_name, context)

        form.save()
        documents_formset.save()

        self.application.section_e_complete = True
        self.application.save(update_fields=['section_e_complete', 'updated_at'])
        return redirect(NEXT_SECTION_URL['e'])


class SummaryView(PaymentRequiredMixin, View):
    template_name = 'admissions/application_summary.html'

    def get(self, request):
        return render(request, self.template_name, {'application': self.application})

    def post(self, request):
        if not self.application.all_sections_complete:
            messages.error(request, 'Please complete all five sections before submitting.')
            return redirect('admissions:dashboard')

        if self.application.status == Application.Status.DRAFT:
            self.application.status = Application.Status.SUBMITTED
            self.application.submitted_at = timezone.now()
            self.application.save(update_fields=['status', 'submitted_at', 'updated_at'])
            messages.success(request, 'Application submitted successfully!')

        return redirect('admissions:summary')


class ApplicationPDFView(PaymentRequiredMixin, View):
    def get(self, request):
        if self.application.status == Application.Status.DRAFT:
            messages.error(request, 'Submit your application before downloading it.')
            return redirect('admissions:summary')

        return render_to_pdf_response(
            'admissions/application_slip_pdf.html',
            {'application': self.application},
            filename=f'application-{self.applicant.id}.pdf',
        )
