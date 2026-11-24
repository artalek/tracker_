from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from math import floor, log10
from threading import Lock

import matplotlib

matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import AutoDateLocator, DateFormatter, date2num
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

render_lock = Lock()


@dataclass(frozen=True)
class RenderedChart:
    png: bytes
    coordinates: list[tuple[float, float]]
    bounds: dict[str, float]


def render_chart(points):
    dates, values = zip(*points)
    rates = [float(value) for value in values]

    with render_lock:
        figure = Figure(figsize=(8, 3.0), dpi=122, facecolor="#ffffff")
        canvas = FigureCanvasAgg(figure)
        axes = figure.add_axes([0.12, 0.17, 0.85, 0.76], facecolor="#ffffff")
        minimum, maximum = min(rates), max(rates)
        padding = (maximum - minimum) * 0.24 or maximum * 0.015
        bottom = max(0, minimum - padding)
        axes.set_ylim(bottom, maximum + padding)
        if len(dates) == 1:
            day = dates[0]
            axes.set_xlim(day - timedelta(days=1), day + timedelta(days=1))
        axes.set_axisbelow(True)
        axes.grid(axis="y", color="#e2e7ee", linewidth=0.8, linestyle="--")
        axes.plot(dates, rates, color="#e62d45", linewidth=2.3, zorder=3)
        axes.fill_between(dates, rates, bottom, color="#e62d45", alpha=0.12)
        axes.scatter(dates[-1], rates[-1], color="#e62d45", s=23, zorder=4)
        for spine in axes.spines.values():
            spine.set_visible(False)
        axes.tick_params(colors="#354156", labelsize=9, length=0, pad=8)
        axes.xaxis.set_major_locator(AutoDateLocator(minticks=3, maxticks=6))
        axes.xaxis.set_major_formatter(DateFormatter("%d.%m"))
        axes.yaxis.set_major_locator(MaxNLocator(nbins=4))
        steps = axes.get_yticks()
        step = steps[1] - steps[0]
        exponent = floor(log10(maximum)) if step < 0.001 else 0
        if exponent:
            axes.set_title(f"×10^{exponent}", loc="left", fontsize=8, color="#354156", pad=4)
        axes.yaxis.set_major_formatter(
            FuncFormatter(lambda value, _: f"{value / 10**exponent:.3f}".replace(".", ",")),
        )
        output = BytesIO()
        canvas.print_png(output)

        width, height = canvas.get_width_height()
        coordinates = [
            (round(x / width * 100, 5), round((1 - y / height) * 100, 5))
            for x, y in axes.transData.transform(list(zip(date2num(dates), rates)))
        ]
        bounds = {
            "left": axes.bbox.x0 / width * 100,
            "right": axes.bbox.x1 / width * 100,
            "top": (1 - axes.bbox.y1 / height) * 100,
            "bottom": (1 - axes.bbox.y0 / height) * 100,
        }
    return RenderedChart(output.getvalue(), coordinates, bounds)
