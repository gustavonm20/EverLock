"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const checks = byId("diagnostics-checks");
  const button = byId("diagnostics-refresh");
  const message = byId("diagnostics-message");
  const summary = byId("diagnostics-summary");
  const checkedAt = byId("diagnostics-checked-at");
  const statuses = { ok: "Disponível", attention: "Requer atenção", info: "Informação" };
  const checkIds = new Set(["application", "database", "face_engine", "biometric_storage", "email", "notifications"]);
  let generation = 0;
  let pending = null;
  let pageSuspended = false;

  function isActive() {
    return !pageSuspended && document.body.dataset.role === "admin"
      && !byId("main").hidden && location.hash === "#diagnostico";
  }

  function clear() {
    generation += 1;
    pending?.abort();
    pending = null;
    checks.replaceChildren();
    checks.setAttribute("aria-busy", "false");
    summary.hidden = true;
    byId("diagnostics-version").textContent = "—";
    checkedAt.textContent = "—";
    checkedAt.removeAttribute("datetime");
    message.textContent = "";
    delete message.dataset.outcome;
    button.disabled = !isActive();
  }

  function validSnapshot(value) {
    return value && typeof value.version === "string" && value.mode === "simulation"
      && typeof value.checked_at === "string" && Number.isFinite(Date.parse(value.checked_at))
      && Array.isArray(value.checks) && value.checks.length === checkIds.size
      && new Set(value.checks.map((check) => check?.id)).size === checkIds.size
      && value.checks.every((check) => check && checkIds.has(check.id)
        && Object.hasOwn(statuses, check.status)
        && [check.title, check.summary, check.detail].every((text) => typeof text === "string"));
  }

  function render(value) {
    const fragment = document.createDocumentFragment();
    for (const check of value.checks) {
      const card = document.createElement("article");
      card.className = "diagnostic-card";
      card.dataset.check = check.id;
      const heading = document.createElement("div");
      heading.className = "diagnostic-heading";
      const title = document.createElement("h3");
      title.textContent = check.title;
      const status = document.createElement("span");
      status.className = "diagnostic-status";
      status.dataset.status = check.status;
      status.textContent = statuses[check.status];
      heading.append(title, status);
      const result = document.createElement("p");
      result.className = "diagnostic-result";
      result.textContent = check.summary;
      const detail = document.createElement("p");
      detail.className = "diagnostic-detail";
      detail.textContent = check.detail;
      card.append(heading, result, detail);
      fragment.append(card);
    }
    checks.replaceChildren(fragment);
    byId("diagnostics-version").textContent = value.version;
    checkedAt.dateTime = value.checked_at;
    checkedAt.textContent = new Date(value.checked_at).toLocaleString("pt-BR");
    summary.hidden = false;
    const count = value.checks.filter((check) => check.status === "attention").length;
    message.textContent = count
      ? `Consulta concluída. ${count === 1 ? "1 item requer" : `${count} itens requerem`} atenção; consulte os detalhes abaixo.`
      : "Consulta concluída. Consulte os detalhes de cada item abaixo.";
  }

  async function refresh() {
    clear();
    if (!isActive()) return;
    const requestGeneration = generation;
    const controller = new AbortController();
    pending = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    const current = () => requestGeneration === generation && isActive();
    button.disabled = true;
    checks.setAttribute("aria-busy", "true");
    message.textContent = "Consultando o diagnóstico…";
    try {
      const response = await fetch("/api/diagnostics", {
        credentials: "same-origin", cache: "no-store", signal: controller.signal,
      });
      if (!current()) return;
      if (response.status === 401) {
        clear();
        document.dispatchEvent(new Event("everlock-login-required"));
        return;
      }
      if (!response.ok) throw new Error("diagnostics-unavailable");
      const value = await response.json();
      if (!current()) return;
      if (!validSnapshot(value)) throw new Error("diagnostics-invalid");
      render(value);
    } catch {
      if (current()) {
        message.textContent = "Não foi possível consultar o diagnóstico. Verifique se o servidor está aberto e tente atualizar novamente.";
        message.dataset.outcome = "error";
      }
    } finally {
      clearTimeout(timeout);
      if (current()) {
        pending = null;
        button.disabled = false;
        checks.setAttribute("aria-busy", "false");
      }
    }
  }

  button.addEventListener("click", refresh);
  window.addEventListener("hashchange", refresh);
  document.addEventListener("everlock-session", refresh);
  document.addEventListener("everlock-login-required", clear);
  byId("logout").addEventListener("click", clear);
  window.addEventListener("pagehide", () => { pageSuspended = true; clear(); });
  window.addEventListener("pageshow", (event) => {
    pageSuspended = false;
    if (event.persisted) refresh();
  });
  refresh();
})();
