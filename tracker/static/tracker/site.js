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

async function loadChart(frame) {
  const state = frame.querySelector("[data-chart-state]");
  const image = frame.querySelector("[data-chart-image]");
  const note = document.querySelector("[data-chart-note]");
  try {
    const response = await fetch(frame.dataset.chart);
    if (!response.ok) {
      const data = await response.json();
      state.textContent = data.error || "Не удалось загрузить график.";
      return;
    }
    const chartUrl = URL.createObjectURL(await response.blob());
    image.src = chartUrl;
    try {
      await image.decode();
    } finally {
      URL.revokeObjectURL(chartUrl);
    }
    image.hidden = false;
    state.hidden = true;
    const date = response.headers.get("X-Rate-Last-Date").split("-").reverse().join(".");
    const stale = response.headers.get("X-Rate-Stale") === "1";
    note.textContent = (stale ? "Сохранённые данные" : "Дневные значения")
      + " · Последний курс за " + date + " · Точек: " + response.headers.get("X-Rate-Points");
  } catch {
    state.textContent = "Не удалось загрузить график. Попробуйте обновить страницу.";
  }
}

const chartFrame = document.querySelector("[data-chart]");
if (chartFrame) loadChart(chartFrame);
