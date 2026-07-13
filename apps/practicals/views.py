import csv

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView, View

from apps.core.constants import Role
from apps.core.mixins import PaginatedListMixin, RoleRequiredMixin

from . import selectors, services
from .forms import PracticalPlacementForm
from .models import PracticalPlacement


class PracticalCoordinatorRoleMixin(RoleRequiredMixin):
    """Only the Practical Coordinator (and Super Admin) manages placement
    sheets - everyone else's access to this data goes through the
    Bursar's own invoice/payment views instead."""
    allowed_roles = (Role.PRACTICAL_COORD, Role.SUPER_ADMIN)


class PracticalPlacementListView(PracticalCoordinatorRoleMixin, PaginatedListMixin, ListView):
    """The placement sheet: everyone who has paid (in full or in part)
    for a Practical fee, ready for the Coordinator to fill in cadre and
    placement location, and download.
    """
    template_name = 'practicals/placement_list.html'
    context_object_name = 'placements'

    def _resolve_fee_type_id(self):
        if hasattr(self, '_fee_type_id'):
            return self._fee_type_id

        requested = self.request.GET.get('fee_type')
        if requested:
            self._fee_type_id = requested
        else:
            default = selectors.get_practical_fee_types().first()
            self._fee_type_id = str(default.pk) if default else None
        return self._fee_type_id

    def get_queryset(self):
        from apps.finance.models import FeeType

        fee_type_id = self._resolve_fee_type_id()
        session_id = self.request.GET.get('session')

        if fee_type_id:
            fee_type = FeeType.objects.filter(pk=fee_type_id).first()
            if fee_type:
                services.sync_placements_for_fee_type(fee_type=fee_type, session=session_id or None)

        return selectors.get_placement_list(fee_type=fee_type_id, session=session_id)

    def get_context_data(self, **kwargs):
        from apps.academics.selectors import get_active_sessions
        from apps.finance.models import FeeType

        context = super().get_context_data(**kwargs)
        context['fee_types'] = FeeType.objects.all()
        context['sessions'] = get_active_sessions()
        context['current_fee_type'] = self._resolve_fee_type_id() or ''
        context['current_session'] = self.request.GET.get('session', '')
        context['querystring'] = self.request.GET.urlencode()
        return context


class PracticalPlacementUpdateView(PracticalCoordinatorRoleMixin, UpdateView):
    """Coordinator fills in the details a placement sheet needs that
    exist nowhere else in the system: other names, cadre, and where the
    student is posted for their practicals.
    """
    model = PracticalPlacement
    form_class = PracticalPlacementForm
    template_name = 'practicals/placement_form.html'
    success_url = reverse_lazy('practicals:placement_list')

    def get_initial(self):
        initial = super().get_initial()
        initial['next'] = self.request.GET.get('next', '')
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = f'Placement Details - {self.object.student.matric_number}'
        context['next'] = self.request.GET.get('next', '')
        return context

    def get_success_url(self):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        return next_url or str(self.success_url)

    def form_valid(self, form):
        messages.success(self.request, f'Placement details saved for {self.object.student.matric_number}.')
        return super().form_valid(form)


class PracticalPlacementExportView(PracticalCoordinatorRoleMixin, View):
    """Downloads the placement sheet in the exact column layout the
    Coordinator hands off: SNO, SURNAME, FIRSTNAME, OTHERNAMES,
    REGISTRATION NUMBER, PHONE NO, CADRE, STATE OF PRACTICAL, LGA OF
    PRACTICAL - one row per student, in the same filtered set shown
    on-screen.
    """

    def get(self, request):
        placements = selectors.get_placement_list(
            fee_type=request.GET.get('fee_type'),
            session=request.GET.get('session'),
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="practical_placement_sheet.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'SNO', 'SURNAME', 'FIRSTNAME', 'OTHERNAMES', 'REGISTRATION NUMBER',
            'PHONE NO', 'CADRE', 'STATE OF PRACTICAL', 'LGA OF PRACTICAL',
        ])
        for index, placement in enumerate(placements, start=1):
            writer.writerow([
                index,
                placement.student.user.last_name.upper(),
                placement.student.user.first_name.upper(),
                placement.other_names.upper(),
                placement.student.matric_number,
                placement.student.user.phone_number,
                placement.cadre.upper(),
                placement.state_of_practical.upper(),
                placement.lga_of_practical.upper(),
            ])
        return response
