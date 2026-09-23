
(function () {
  "use strict";

  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function initAlerts() {
    $$(".alert[data-autohide]").forEach((alert) => {
      const delay = parseInt(alert.dataset.autohide, 10) || 5000;
      setTimeout(() => {
        if (!document.body.contains(alert)) return;
        if (window.bootstrap) {
          window.bootstrap.Alert.getOrCreateInstance(alert).close();
        } else {
          alert.remove();
        }
      }, delay);
    });
  }

  function initForms() {
    document.addEventListener("submit", (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;

      const message = form.dataset.confirm;
      if (message && !window.confirm(message)) {
        event.preventDefault();
        return;
      }
      if (form.hasAttribute("data-no-lock")) return;

      const button = event.submitter || form.querySelector('[type="submit"]');
      if (!button) return;
      setTimeout(() => {
        button.dataset.originalHtml = button.innerHTML;
        button.disabled = true;
        const text = form.dataset.loadingText || "Please wait...";
        button.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>';
        button.append(document.createTextNode(text));
      }, 0);
    });

    window.addEventListener("pageshow", (event) => {
      if (!event.persisted) return;
      $$("button[data-original-html]").forEach((button) => {
        button.innerHTML = button.dataset.originalHtml;
        button.disabled = false;
      });
    });

    $$("form[data-autosubmit] select").forEach((select) => {
      select.addEventListener("change", () => select.form.requestSubmit());
    });
  }

  const DEFAULT_MAX_FILES = 5;
  const DEFAULT_MAX_MB = 5;
  const DEFAULT_ALLOWED = [".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx"];

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function initFileInputs() {
    $$('input[type="file"][multiple]').forEach((input) => {
      const maxFiles = parseInt(input.dataset.maxFiles, 10) || DEFAULT_MAX_FILES;
      const maxMb = parseFloat(input.dataset.maxSizeMb) || DEFAULT_MAX_MB;
      const allowed = input.dataset.allowed
        ? input.dataset.allowed.split(",").map((s) => s.trim().toLowerCase())
        : DEFAULT_ALLOWED;

      const list = document.createElement("ul");
      list.className = "file-list list-unstyled mb-0 mt-2";
      input.insertAdjacentElement("afterend", list);

      input.addEventListener("change", () => {
        list.replaceChildren();
        const files = Array.from(input.files);
        let problem = "";

        if (files.length > maxFiles) {
          problem = "Please choose at most " + maxFiles + " files.";
        }

        files.forEach((file) => {
          const dot = file.name.lastIndexOf(".");
          const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
          let error = "";
          if (!allowed.includes(extension)) {
            error = "type not allowed";
          } else if (file.size > maxMb * 1024 * 1024) {
            error = "larger than " + maxMb + " MB";
          }

          const item = document.createElement("li");
          item.className = error ? "text-danger" : "text-success";
          item.textContent = (error ? "\u2717 " : "\u2713 ") + file.name + " (" + formatSize(file.size) + ")" + (error ? " - " + error : "");
          list.appendChild(item);

          if (error && !problem) problem = '"' + file.name + '": ' + error + ".";
        });

        input.setCustomValidity(problem);
        input.classList.toggle("is-invalid", Boolean(problem));
        if (problem) input.reportValidity();
      });
    });
  }

  function initTooltips() {
    if (!window.bootstrap) return;
    $$('[data-bs-toggle="tooltip"]').forEach((el) => new window.bootstrap.Tooltip(el));
  }

  function initNavHighlight() {
    $$(".navbar-cms .nav-link").forEach((link) => {
      if (link.pathname === window.location.pathname) link.classList.add("active");
    });
  }

  const PALETTES = {
    status: ["#dc3545", "#ffc107", "#198754", "#6c757d"],     
    priority: ["#6c757d", "#0dcaf0", "#fd7e14", "#dc3545"],  
    category: ["#0d6efd", "#6f42c1", "#d63384", "#fd7e14", "#20c997", "#198754", "#0dcaf0", "#6610f2"],
  };

  function readJson(id) {
    const element = document.getElementById(id);
    return element ? JSON.parse(element.textContent) : null;
  }

  function showNoData(canvas) {
    const note = document.createElement("p");
    note.className = "text-muted text-center my-5";
    note.textContent = "No data yet";
    canvas.replaceWith(note);
  }

  function initCharts() {
    if (typeof Chart === "undefined") return;

    $$("canvas[data-chart]").forEach((canvas) => {
      const data = readJson(canvas.dataset.source);
      if (!data) return;

      const type = canvas.dataset.chart;

      if (type === "line") {
        new Chart(canvas, {
          type: "line",
          data: {
            labels: data.labels,
            datasets: [
              {
                label: "Created",
                data: data.created,
                borderColor: "#0d6efd",
                backgroundColor: "rgba(13, 110, 253, 0.12)",
                fill: true,
                tension: 0.3,
                pointRadius: 2,
              },
              {
                label: "Resolved",
                data: data.resolved,
                borderColor: "#198754",
                backgroundColor: "rgba(25, 135, 84, 0.12)",
                fill: true,
                tension: 0.3,
                pointRadius: 2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: { legend: { position: "bottom" } },
            scales: {
              y: { beginAtZero: true, ticks: { precision: 0 } },
              x: { ticks: { maxTicksLimit: 10 } },
            },
          },
        });
        return;
      }

      if (!data.values.some((value) => value > 0)) {
        showNoData(canvas);
        return;
      }

      const palette = PALETTES[canvas.dataset.palette] || PALETTES.category;
      const colors = data.labels.map((_, i) => palette[i % palette.length]);

      if (type === "doughnut") {
        new Chart(canvas, {
          type: "doughnut",
          data: { labels: data.labels, datasets: [{ data: data.values, backgroundColor: colors, borderWidth: 0 }] },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "62%",
            plugins: { legend: { position: "bottom" } },
          },
        });
      } else if (type === "bar") {
        const horizontal = canvas.hasAttribute("data-horizontal");
        const valueAxis = { beginAtZero: true, ticks: { precision: 0 } };
        new Chart(canvas, {
          type: "bar",
          data: {
            labels: data.labels,
            datasets: [{ data: data.values, backgroundColor: colors, borderRadius: 6 }],
          },
          options: {
            indexAxis: horizontal ? "y" : "x",
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: horizontal ? { x: valueAxis } : { y: valueAxis },
          },
        });
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initAlerts();
    initForms();
    initFileInputs();
    initTooltips();
    initNavHighlight();
    initCharts();
  });
})();