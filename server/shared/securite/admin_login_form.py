"""Django administration sign-in form: password, then a second factor code (ADR-028)."""
from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError

from . import two_factor


class AdminLoginForm(AdminAuthenticationForm):
    code = forms.CharField(
        label='Code de double authentification', max_length=20,
        widget=forms.TextInput(attrs={'autocomplete': 'one-time-code', 'inputmode': 'numeric'}),
        help_text="Code à 6 chiffres de l'application, ou code de secours.",
    )

    def confirm_login_allowed(self, user):
        """Called once the password is right: the code is then checked, never before."""
        super().confirm_login_allowed(user)
        result = two_factor.check_admin_code(user, self.cleaned_data.get('code', ''), self.request)
        if result == two_factor.NOT_ENABLED:
            raise ValidationError("Activez d'abord la double authentification depuis le back-office du site.",
                                  code='two_factor_not_enabled')
        if result != two_factor.VERIFIED:
            raise ValidationError('Code de double authentification incorrect ou déjà utilisé.',
                                  code='two_factor_invalid')
