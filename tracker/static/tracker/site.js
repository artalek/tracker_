const converter = document.querySelector("[data-converter]");
if (converter) {
  const swap = converter.querySelector("[data-swap]");
  const base = converter.elements.namedItem("base");
  const target = converter.elements.namedItem("target");
  swap.hidden = false;
  swap.addEventListener("click", () => {
    [base.value, target.value] = [target.value, base.value];
  });
}

function enablePointInspection(frame, points, bounds) {
  const plot = frame.querySelector("[data-chart-plot]");
  const crosshair = plot.querySelector("[data-chart-crosshair]");
  const marker = plot.querySelector("[data-chart-marker]");
  const tooltip = plot.querySelector("[data-chart-tooltip]");
  const rate = tooltip.querySelector("[data-chart-rate]");
  const date = tooltip.querySelector("[data-chart-date]");
  const announcement = plot.querySelector("[data-chart-announcement]");
  let active = null;

  plot.style.setProperty("--plot-top", bounds.top + "%");
  plot.style.setProperty("--plot-bottom", bounds.bottom + "%");

  function show(index, announce = false) {
    const point = points[index];
    if (active !== index) {
      active = index;
      plot.style.setProperty("--point-x", point.x + "%");
      plot.style.setProperty("--point-y", point.y + "%");
      tooltip.classList.toggle("below", point.y < 42);
      rate.textContent = point.rate + " " + frame.dataset.quote;
      date.textContent = point.date;
      date.dateTime = point.date.split(".").reverse().join("-");
      crosshair.hidden = marker.hidden = tooltip.hidden = false;
    }
    if (announce) {
      announcement.textContent = rate.textContent + ", " + point.date;
    }
  }

  function hide() {
    active = null;
    crosshair.hidden = marker.hidden = tooltip.hidden = true;
  }

  function inspectPointer(event) {
    const box = plot.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width * 100;
    const y = (event.clientY - box.top) / box.height * 100;
    if (x < bounds.left || x > bounds.right || y < bounds.top || y > bounds.bottom) {
      hide();
      return;
    }
    const nearest = points.reduce((best, point, index) =>
      Math.abs(point.x - x) < Math.abs(points[best].x - x) ? index : best, 0);
    show(nearest);
  }

  plot.addEventListener("pointermove", (event) => {
    if (event.pointerType !== "touch" || event.buttons) inspectPointer(event);
  });
  plot.addEventListener("pointerdown", inspectPointer);
  plot.addEventListener("pointerleave", (event) => {
    if (event.pointerType !== "touch") hide();
  });
  plot.addEventListener("blur", hide);
  plot.addEventListener("keydown", (event) => {
    const last = points.length - 1;
    let index;
    switch (event.key) {
      case "ArrowLeft": index = Math.max(0, (active ?? last + 1) - 1); break;
      case "ArrowRight": index = Math.min(last, (active ?? -1) + 1); break;
      case "Home": index = 0; break;
      case "End": index = last; break;
      case "Escape": hide(); return;
      default: return;
    }
    event.preventDefault();
    show(index, true);
  });
}

async function loadChart(frame) {
  const state = frame.querySelector("[data-chart-state]");
  const plot = frame.querySelector("[data-chart-plot]");
  const image = frame.querySelector("[data-chart-image]");
  const note = document.querySelector("[data-chart-note]");
  try {
    const response = await fetch(frame.dataset.chart);
    const data = await response.json();
    if (!response.ok) {
      state.textContent = data.error || "Не удалось загрузить график.";
      return;
    }
    image.src = "data:image/png;base64," + data.image;
    await image.decode();
    enablePointInspection(frame, data.points, data.bounds);
    plot.hidden = false;
    state.hidden = true;
    const lastDate = data.points.at(-1).date;
    note.textContent = (data.stale ? "Сохранённые данные" : "Дневные значения")
      + " · Последний курс за " + lastDate + " · Точек: " + data.points.length;
  } catch {
    state.textContent = "Не удалось загрузить график. Попробуйте обновить страницу.";
  }
}

const chartFrame = document.querySelector("[data-chart]");
if (chartFrame) loadChart(chartFrame);
