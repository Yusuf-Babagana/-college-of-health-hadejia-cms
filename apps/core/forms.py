from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit


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
