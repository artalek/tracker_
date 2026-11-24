from base64 import b64encode

from django.http import HttpResponse, JsonResponse
from django.template.defaultfilters import floatformat
from django.views.decorators.http import require_GET

from .forms import ChartForm
from .services import RateService


@require_GET
def chart_image(request):
    form = ChartForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"error": "Проверьте валютную пару и период."}, status=400)

    points, stale = RateService().history(**form.cleaned_data)
    if not points:
        return JsonResponse(
            {"error": "За выбранный период курсы недоступны. Попробуйте позже или измените период."},
            status=503 if stale else 404,
        )

    # Load Matplotlib only for graph requests.
    from .charts import render_chart

    chart = render_chart(tuple(points))
    if request.GET.get("format") == "interactive":
        response = JsonResponse({
            "image": b64encode(chart.png).decode("ascii"),
            "bounds": chart.bounds,
            "points": [
                {"x": x, "y": y, "date": day.strftime("%d.%m.%Y"), "rate": floatformat(rate, "3")}
                for (day, rate), (x, y) in zip(points, chart.coordinates, strict=True)
            ],
            "stale": stale,
        })
    else:
        response = HttpResponse(chart.png, content_type="image/png")
    response["X-Rate-Points"] = str(len(points))
    response["X-Rate-Last-Date"] = points[-1][0].isoformat()
    response["X-Rate-Stale"] = "1" if stale else "0"
    response["Cache-Control"] = "no-store" if stale else "public, max-age=900"
    return response
