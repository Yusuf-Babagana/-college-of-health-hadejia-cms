from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit


class DepartmentScopedSelect(forms.Select):
    """A <select> whose <option>s each carry a data-department="<id>"
    attribute, so a small JS snippet (see static/js/department-scoped-select.js)
    can filter them client-side to match whatever Department is currently
    selected elsewhere in the same form - e.g. narrowing the Programme
    dropdown to the chosen Department without a page reload or an extra
    AJAX endpoint.

    ``department_by_value`` maps each option's field value (as a string)
    to its owning department's id (also as a string).
    """

    def __init__(self, *args, department_by_value=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.department_by_value = department_by_value or {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        department_id = self.department_by_value.get(str(value))
        if department_id:
            option['attrs']['data-department'] = str(department_id)
        return option


class CrispyFormMixin:
    """Mix into any Form/ModelForm to get a crispy-forms helper with a
    single submit button, so every form in the project renders the same
    way via {% crispy form %} without repeating this boilerplate.
    """
    submit_label = 'Submit'
    submit_css_class = 'btn btn-primary w-100'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.add_input(Submit('submit', self.submit_label, css_class=self.submit_css_class))
