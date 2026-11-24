from io import BytesIO
from threading import Lock

import matplotlib

matplotlib.use("Agg")

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import AutoDateLocator, DateFormatter
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

render_lock = Lock()


def render_chart(points):
    dates, rates = zip(*points)
    rates = [float(rate) for rate in rates]

    with render_lock:
        figure = Figure(figsize=(8, 3.0), dpi=122, facecolor="#101b2d")
        axes = figure.add_axes([0.12, 0.16, 0.85, 0.79], facecolor="#101b2d")
        figure_canvas = FigureCanvasAgg(figure)
        minimum, maximum = min(rates), max(rates)
        padding = (maximum - minimum) * 0.24 or maximum * 0.015
        axes.set_ylim(minimum - padding, maximum + padding)
        axes.set_axisbelow(True)
        axes.grid(axis="y", color="#26354d", linewidth=0.8, linestyle="--")
        axes.plot(dates, rates, color="#54e5c5", linewidth=2.3, zorder=3)
        axes.fill_between(dates, rates, minimum - padding, color="#54e5c5", alpha=0.11)
        axes.scatter(dates[-1], rates[-1], color="#8cf7dd", s=23, zorder=4)
        for spine in axes.spines.values():
            spine.set_visible(False)
        axes.tick_params(colors="#a3b4ce", labelsize=9, length=0, pad=8)
        axes.xaxis.set_major_locator(AutoDateLocator(minticks=3, maxticks=6))
        axes.xaxis.set_major_formatter(DateFormatter("%d.%m"))
        axes.yaxis.set_major_locator(MaxNLocator(nbins=4))
        axes.yaxis.set_major_formatter(StrMethodFormatter("{x:.6g}"))
        output = BytesIO()
        figure_canvas.print_png(output)
    return output.getvalue()
