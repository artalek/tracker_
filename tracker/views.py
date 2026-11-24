from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import ChartForm, ConversionForm, DistinctPairForm, RegistrationForm
from .models import Conversion, Currency, Favorite
from .services import CurrencyConverter, RateError, RateService

DEFAULT_PAIR = {"base": "USD", "target": "EUR", "days": 30}
POPULAR_QUOTES = ("EUR", "GBP", "RUB", "KZT")


def conversion_result_from_session(request):
    result = request.session.pop("conversion_result", None)
    if result is not None:
        for key in ("amount", "result", "rate"):
            result[key] = Decimal(result[key])
        result["date"] = date.fromisoformat(result["date"])
    return result


def submit_conversion(request, form, days):
    base = form.cleaned_data["base"]
    target = form.cleaned_data["target"]
    try:
        result = CurrencyConverter().convert(form.cleaned_data["amount"], base, target, user=request.user)
    except RateError as exc:
        form.add_error(None, str(exc))
        return None

    request.session["conversion_result"] = {
        "base": base.code, "target": target.code, "amount": str(result.amount),
        "result": str(result.result), "rate": str(result.rate),
        "date": result.rate_date.isoformat(), "stale": result.stale,
    }
    if base == target:
        return redirect("tracker:home")
    return redirect(
        f"{reverse('tracker:home')}?base={base.code}&target={target.code}&days={days}",
    )


def overview_rates():
    currencies = Currency.objects.filter(is_active=True).in_bulk(
        ("USD", *POPULAR_QUOTES), field_name="code",
    )
    quotes = [currencies[code] for code in POPULAR_QUOTES if code in currencies]
    latest = RateService().latest(currencies["USD"], quotes) if "USD" in currencies else {}
    return [(quote, latest.get(quote.code)) for quote in quotes]


@never_cache
@require_http_methods(["GET", "POST"])
def home(request):
    chart_form = ChartForm({**DEFAULT_PAIR, **request.GET.dict()}, auto_id="chart_%s")
    chart = chart_form.cleaned_data if chart_form.is_valid() else None
    result = conversion_result_from_session(request) if request.method == "GET" else None
    initial = {"amount": Decimal("100"), "base": "USD", "target": "EUR"}
    if chart:
        initial.update(base=chart["base"].code, target=chart["target"].code)
    if result is not None:
        initial.update(amount=result["amount"], base=result["base"], target=result["target"])
    form = ConversionForm(request.POST if request.method == "POST" else None, initial=initial)

    if request.method == "POST" and form.is_valid():
        response = submit_conversion(request, form, chart["days"] if chart else DEFAULT_PAIR["days"])
        if response is not None:
            return response

    return render(request, "tracker/home.html", {
        "form": form, "result": result, "chart_form": chart_form, "chart": chart,
        "cards": overview_rates(),
    })


@require_GET
def legal_page(request, template_name):
    return render(request, template_name, {
        "operator": settings.PRIVACY_OPERATOR_NAME,
        "contact": settings.PRIVACY_CONTACT_EMAIL,
    })


@require_GET
def rates(request):
    currencies = {currency.code: currency for currency in Currency.objects.filter(is_active=True)}
    default = "USD" if "USD" in currencies else next(iter(currencies), "")
    code = request.GET.get("base", default)
    base = currencies.get(code)
    targets = [currency for currency in currencies.values() if currency != base]
    snapshots = RateService().latest(base, targets) if base else {}
    favorite_ids = set()
    if base and request.user.is_authenticated:
        favorite_ids = set(Favorite.objects.filter(user=request.user, base_currency=base).values_list(
            "target_currency_id", flat=True,
        ))
    return render(request, "tracker/rates.html", {
        "base": base, "currencies": currencies.values(),
        "invalid_base": bool(code and not base),
        "rows": [(target, snapshots.get(target.code), target.pk in favorite_ids) for target in targets] if base else [],
    })


@login_required
@never_cache
@require_GET
def dashboard(request):
    favorites = Favorite.objects.filter(user=request.user).select_related("base_currency", "target_currency")
    conversions = Conversion.objects.filter(user=request.user).select_related("base_currency", "target_currency")
    return render(request, "tracker/dashboard.html", {
        "favorites": favorites,
        "history": Paginator(conversions, 10).get_page(request.GET.get("page")),
    })


@login_required
@require_POST
def add_favorite(request):
    form = DistinctPairForm(request.POST)
    valid = form.is_valid()
    if valid:
        _, created = Favorite.objects.get_or_create(
            user=request.user, base_currency=form.cleaned_data["base"],
            target_currency=form.cleaned_data["target"],
        )
        messages.success(request, "Пара добавлена в избранное." if created else "Пара уже в избранном.")
    else:
        messages.error(request, "Выберите две разные доступные валюты.")
    if request.POST.get("source") == "rates" and valid:
        return redirect(f"{reverse('tracker:rates')}?base={form.cleaned_data['base'].code}")
    return redirect("tracker:dashboard")


@login_required
@require_POST
def remove_favorite(request, pk):
    deleted, _ = Favorite.objects.filter(user=request.user, pk=pk).delete()
    if not deleted:
        return HttpResponse(status=404)
    messages.success(request, "Пара удалена из избранного.")
    return redirect("tracker:dashboard")


@never_cache
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("tracker:dashboard")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        return redirect("tracker:dashboard")
    return render(request, "tracker/register.html", {"form": form})
