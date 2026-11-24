from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import ChartForm, ConversionForm, DistinctPairForm, RegistrationForm
from .models import Conversion, Currency, Favorite
from .services import CurrencyConverter, RateError, RateService

DEFAULT_PAIR = {"base": "USD", "target": "EUR", "days": 30}
POPULAR_QUOTES = ("EUR", "GBP", "RUB", "KZT")


def chart_data(form):
    return form.cleaned_data if form.is_valid() else None


@never_cache
@require_http_methods(["GET", "POST"])
def home(request):
    chart_form = ChartForm({**DEFAULT_PAIR, **request.GET.dict()}, auto_id="chart_%s")
    chart = chart_data(chart_form)
    saved = request.session.pop("conversion_result", None) if request.method == "GET" else None
    initial = {"amount": Decimal("100"), "base": "USD", "target": "EUR"}
    if chart:
        initial.update(base=chart["base"].code, target=chart["target"].code)
    if saved is not None:
        initial.update(amount=Decimal(saved["amount"]), base=saved["base"], target=saved["target"])
    form = ConversionForm(request.POST if request.method == "POST" else None, initial=initial)

    if request.method == "POST" and form.is_valid():
        base, target, amount = (form.cleaned_data[key] for key in ("base", "target", "amount"))
        try:
            result = CurrencyConverter().convert(amount, base, target)
        except RateError as exc:
            form.add_error(None, str(exc))
        else:
            if request.user.is_authenticated:
                Conversion.objects.create(
                    user=request.user, base_currency=base, target_currency=target,
                    amount=result.amount, result=result.result, rate=result.rate, rate_date=result.rate_date,
                )
            request.session["conversion_result"] = {
                "base": base.code, "target": target.code, "amount": str(result.amount),
                "result": str(result.result), "rate": str(result.rate),
                "date": result.rate_date.isoformat(), "stale": result.stale,
            }
            if base != target:
                days = chart["days"] if chart else DEFAULT_PAIR["days"]
                return redirect(
                    f"{reverse('tracker:home')}?base={base.code}&target={target.code}&days={days}",
                )
            return redirect("tracker:home")

    if saved:
        for key in ("amount", "result", "rate"):
            saved[key] = Decimal(saved[key])
        saved["date"] = date.fromisoformat(saved["date"])

    currencies = Currency.objects.filter(is_active=True).in_bulk(
        ("USD", *POPULAR_QUOTES), field_name="code",
    )
    quotes = [currencies[code] for code in POPULAR_QUOTES if code in currencies]
    latest = RateService().latest(currencies["USD"], quotes) if "USD" in currencies else {}
    return render(request, "tracker/home.html", {
        "form": form, "result": saved, "chart_form": chart_form, "chart": chart,
        "cards": [(quote, latest.get(quote.code)) for quote in quotes],
    })


@require_GET
def chart_image(request):
    form = ChartForm(request.GET)
    chart = chart_data(form)
    if chart is None:
        return JsonResponse({"error": "Проверьте валютную пару и период."}, status=400)

    points, stale = RateService().history(chart["base"], chart["target"], chart["days"])
    if not points:
        return JsonResponse(
            {"error": "За выбранный период курсы недоступны. Попробуйте позже или измените период."},
            status=503 if stale else 404,
        )

    from .charts import render_chart

    response = HttpResponse(render_chart(points), content_type="image/png")
    response["X-Rate-Points"] = str(len(points))
    response["X-Rate-Last-Date"] = points[-1][0].isoformat()
    response["X-Rate-Stale"] = "1" if stale else "0"
    response["Cache-Control"] = "no-store" if stale else "public, max-age=900"
    return response


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
