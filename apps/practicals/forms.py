from django import forms

from apps.core.forms import CrispyFormMixin

from .models import PracticalPlacement


class PracticalPlacementForm(CrispyFormMixin, forms.ModelForm):
    """The 'next' field is not a model field - it's a hidden pass-through
    so the page the Coordinator came from (a filtered placement list) is
    where they land after saving, instead of always the unfiltered list.
    """
    submit_label = 'Save Placement Details'
    next = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = PracticalPlacement
        fields = ('other_names', 'cadre', 'state_of_practical', 'lga_of_practical')
        labels = {
            'other_names': 'Other Names',
            'cadre': 'Cadre',
            'state_of_practical': 'State of Practical',
            'lga_of_practical': 'LGA of Practical',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(['other_names', 'cadre', 'state_of_practical', 'lga_of_practical', 'next'])
