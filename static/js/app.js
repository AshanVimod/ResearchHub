/* Research Hub — shared client behaviour: theme, shortcuts, confirm modal, timer, quick capture. */
(function () {
  "use strict";

  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;

  window.rhFetch = function (url, opts = {}) {
    opts.headers = Object.assign({ "X-CSRFToken": csrf(), "Content-Type": "application/json" }, opts.headers || {});
    if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
    return fetch(url, opts).then(async (r) => {
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
      return data;
    });
  };

  // ---- toasts ---------------------------------------------------------------
  window.rhToast = function (message, kind = "success") {
    const icon = { success: "bi-check-circle text-success", danger: "bi-exclamation-octagon text-danger",
                   warning: "bi-exclamation-triangle text-warning" }[kind] || "bi-info-circle";
    const el = document.createElement("div");
    el.className = "toast show align-items-center";
    el.setAttribute("role", "status");
    el.innerHTML = `<div class="d-flex"><div class="toast-body d-flex gap-2"><i class="bi ${icon}" aria-hidden="true"></i><span></span></div>
      <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Dismiss"></button></div>`;
    el.querySelector("span").textContent = message;
    document.getElementById("toasts").appendChild(el);
    autohide(el);
  };
  function autohide(el) {
    setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 200); }, 4500);
  }
  document.querySelectorAll(".toast[data-autohide]").forEach(autohide);
  document.addEventListener("click", (e) => {
    const b = e.target.closest('[data-bs-dismiss="toast"]');
    if (b) b.closest(".toast").remove();
  });

  // ---- copy to clipboard: data-copy="text" or data-copy-from="#selector" -------------
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-copy], [data-copy-from]");
    if (!b) return;
    const text = b.dataset.copy ?? (document.querySelector(b.dataset.copyFrom) || {}).value ?? "";
    navigator.clipboard.writeText(text)
      .then(() => rhToast("Copied to clipboard."))
      .catch(() => rhToast("Could not copy. Select the text and press Ctrl+C.", "warning"));
  });

  // ---- sortable tables: <table data-sortable>, header <button class="sort-btn" data-type="num|text">, cells data-sort ----
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("table[data-sortable] .sort-btn");
    if (!btn) return;
    const th = btn.closest("th"), table = th.closest("table"), idx = [...th.parentNode.children].indexOf(th);
    const dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
    table.querySelectorAll("thead th[aria-sort]").forEach((h) => h.setAttribute("aria-sort", "none"));
    th.setAttribute("aria-sort", dir);
    const num = btn.dataset.type === "num", body = table.tBodies[0];
    const key = (tr) => { const c = tr.children[idx]; const v = c ? (c.dataset.sort ?? c.textContent.trim()) : "";
      return num ? (v === "" ? NaN : parseFloat(v)) : v.toLowerCase(); };
    [...body.rows].sort((a, b) => {
      const x = key(a), y = key(b);
      if (num) { if (isNaN(x)) return 1; if (isNaN(y)) return -1; return dir === "ascending" ? x - y : y - x; }
      return dir === "ascending" ? x.localeCompare(y) : y.localeCompare(x);
    }).forEach((tr) => body.appendChild(tr));
  });

  // ---- theme ------------------------------------------------------------------
  function syncThemeIcon() {
    const dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    document.querySelectorAll("[data-theme-toggle] i").forEach((i) => {
      i.className = "bi " + (dark ? "bi-sun" : "bi-moon-stars");
    });
    document.dispatchEvent(new CustomEvent("rh:theme"));
  }
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-theme-toggle]")) return;
    const next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-bs-theme", next);
    try { localStorage.setItem("rh-theme", next); } catch (_) {}
    syncThemeIcon();
  });
  syncThemeIcon();

  // ---- mobile menu ------------------------------------------------------------
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-menu]");
    const side = document.getElementById("sidebar");
    if (btn) {
      const open = side.classList.toggle("open");
      btn.setAttribute("aria-expanded", open);
      return;
    }
    if (side.classList.contains("open") && !e.target.closest("#sidebar")) side.classList.remove("open");
  });

  // ---- confirm modal for destructive forms (no browser dialogs) ---------------
  let pendingForm = null;
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!form.matches("[data-confirm]") || form.dataset.confirmed) return;
    e.preventDefault();
    pendingForm = form;
    document.getElementById("confirm-text").textContent = form.dataset.confirm;
    document.getElementById("confirm-go").textContent = form.dataset.confirmLabel || "Delete";
    bootstrap.Modal.getOrCreateInstance("#confirm-modal").show();
  });
  document.getElementById("confirm-go").addEventListener("click", () => {
    if (!pendingForm) return;
    pendingForm.dataset.confirmed = "1";
    bootstrap.Modal.getOrCreateInstance("#confirm-modal").hide();
    pendingForm.requestSubmit();
  });

  // ---- form modal loaded over HTMX -------------------------------------------
  window.rhOpenForm = function (url) {
    htmx.ajax("GET", url, { target: "#form-modal-content", swap: "innerHTML" }).then(() => {
      const m = bootstrap.Modal.getOrCreateInstance("#form-modal");
      m.show();
      setTimeout(() => {
        const f = document.querySelector("#form-modal-content [autofocus]");
        if (f) f.focus();
      }, 180);
    });
  };
  document.body.addEventListener("htmx:beforeSwap", (e) => {
    if (e.detail.xhr.status === 422) { e.detail.shouldSwap = true; e.detail.isError = false; }
  });

  // ---- Alpine components ------------------------------------------------------
  window.capture = function () {
    return {
      text: "", busy: false,
      save() {
        if (!this.text.trim()) return;
        this.busy = true;
        rhFetch("/api/inbox", { method: "POST", body: { text: this.text } })
          .then((d) => {
            this.text = "";
            rhToast("Captured to inbox.");
            document.querySelectorAll('.side-link[href="/inbox"] .count').forEach((c) => (c.textContent = d.count));
          })
          .catch((err) => rhToast(err.message, "danger"))
          .finally(() => (this.busy = false));
      },
    };
  };

  const pad = (n) => String(n).padStart(2, "0");
  window.timerWidget = function () {
    return {
      running: false, busy: false, stale: false, category: "writing", startedAt: null, offset: 0, elapsed: 0,
      staleEnd: "", tick: null,
      get display() {
        const s = this.elapsed, h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
        return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
      },
      get startedLabel() {
        return this.startedAt ? new Date(this.startedAt).toLocaleString() : "";
      },
      init() {
        try { this.category = localStorage.getItem("rh-timer-cat") || this.category; } catch (_) {}
        this.$watch("category", (v) => { try { localStorage.setItem("rh-timer-cat", v); } catch (_) {} });
        this.load();
        setInterval(() => this.load(), 30000);
        this.tick = setInterval(() => { if (this.running) this.elapsed = Math.max(0, Math.round((Date.now() - this.offset) / 1000)); }, 1000);
        window.addEventListener("rh:timer-toggle", () => this.toggle());
      },
      apply(s) {
        this.running = !!s.running;
        if (s.running) {
          this.category = s.category;
          this.startedAt = s.started_at;
          this.elapsed = s.elapsed;
          this.offset = Date.now() - s.elapsed * 1000;
          if (s.stale && !this.staleEnd) {
            const d = new Date(s.started_at); d.setHours(d.getHours() + 2);
            this.staleEnd = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
            this.stale = true;
          }
        } else { this.elapsed = 0; this.stale = false; }
      },
      load() { fetch("/api/timer").then((r) => r.json()).then((s) => this.apply(s)).catch(() => {}); },
      toggle() {
        if (this.busy) return;
        this.busy = true;
        const req = this.running
          ? rhFetch("/api/timer/stop", { method: "POST", body: {} }).then((d) => { rhToast(`Logged ${d.minutes} min of ${this.category}.`); this.apply({ running: false }); document.dispatchEvent(new CustomEvent("rh:time-changed")); })
          : rhFetch("/api/timer/start", { method: "POST", body: { category: this.category } }).then((s) => this.apply(s));
        req.catch((e) => rhToast(e.message, "danger")).finally(() => (this.busy = false));
      },
      stopAt() {
        rhFetch("/api/timer/stop", { method: "POST", body: { ended_at: this.staleEnd + ":00" } })
          .then((d) => { rhToast(`Logged ${d.minutes} min.`); this.apply({ running: false }); })
          .catch((e) => rhToast(e.message, "danger"));
      },
    };
  };

  // ---- keyboard shortcuts: / search, Alt+N capture, Alt+T timer ---------------
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
    if (e.key === "?" && !typing) {
      e.preventDefault();
      bootstrap.Modal.getOrCreateInstance("#keys-modal").show();
    } else if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      document.getElementById("global-search").focus();
    } else if (e.altKey && (e.key === "n" || e.key === "N")) {
      e.preventDefault();
      const q = document.getElementById("quick-capture");
      if (q && q.offsetParent) q.focus(); else location.href = "/inbox";
    } else if (e.altKey && (e.key === "t" || e.key === "T")) {
      e.preventDefault();
      window.dispatchEvent(new CustomEvent("rh:timer-toggle"));
    }
  });

  // ---- chart colours from CSS tokens ------------------------------------------
  window.rhToken = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
})();
