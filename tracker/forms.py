from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Currency

PERIODS = [(7, "7 дней"), (30, "30 дней"), (90, "90 дней"), (365, "1 год")]


class PairForm(forms.Form):
    base = forms.ModelChoiceField(
        label="Из валюты", queryset=Currency.objects.none(), to_field_name="code", empty_label=None,
    )
    target = forms.ModelChoiceField(
        label="В валюту", queryset=Currency.objects.none(), to_field_name="code", empty_label=None,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        currencies = Currency.objects.filter(is_active=True)
        self.fields["base"].queryset = currencies
        self.fields["target"].queryset = currencies


class ConversionForm(PairForm):
    amount = forms.DecimalField(
        label="Сумма", min_value=Decimal("0.000001"), max_digits=16, decimal_places=6,
        localize=True, widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
    )


class DistinctPairForm(PairForm):
    def clean(self):
        cleaned = super().clean()
        if cleaned.get("base") and cleaned["base"] == cleaned.get("target"):
            self.add_error("target", "Выберите две разные валюты.")
        return cleaned


class ChartForm(DistinctPairForm):
    days = forms.TypedChoiceField(label="Период", choices=PERIODS, coerce=int)


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(label="Электронная почта", required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")
