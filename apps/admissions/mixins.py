from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect

from apps.core.constants import Role


class ApplicantRequiredMixin(AccessMixin):
    """Restricts a view to logged-in Role.APPLICANT users, redirecting to
    the admissions portal's own login page rather than the main CMS's
    accounts:login (the global LOGIN_URL default).

    All gating happens in dispatch(), before Django resolves the request to
    self.get()/self.post() - a subclass defining its own get()/post() (as
    every section view does) would otherwise silently shadow a check placed
    in a mixin's get()/post() instead.
    """

    login_url = 'admissions:login'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != Role.APPLICANT:
            return self.handle_no_permission()

        self.applicant = request.user.applicant_profile
        self.application = self.applicant.application

        blocked = self.check_access(request)
        if blocked is not None:
            return blocked

        return super().dispatch(request, *args, **kwargs)

    def check_access(self, request):
        """Hook for subclasses to add extra gating. Return None to allow
        the request through, or an HttpResponse (e.g. a redirect) to
        short-circuit before the view's get()/post() ever runs.
        """
        return None


class PaymentRequiredMixin(ApplicantRequiredMixin):
    """Additionally requires the applicant to have paid (or redeemed a
    referral code) before reaching the application form/summary/PDF.
    """

    def check_access(self, request):
        if not self.applicant.has_paid:
            messages.info(request, 'Please pay the application fee or enter a referral code first.')
            return redirect('admissions:referral_check')
        return super().check_access(request)
