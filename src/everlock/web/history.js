"use strict";

// Uma única dona do histórico; o polling da porta não substitui páginas antigas.
(() => {
  const form = document.getElementById("history-filter");
  const events = document.getElementById("events");
  const note = document.getElementById("history-note");
  const more = document.getElementById("history-more");
  const refresh = document.getElementById("history-refresh");
  const exportButton = document.getElementById("history-export");
  let generation = 0, pending = null, cursor = null, exportCursor = null, count = 0;
  let exporting = false;
  let applied = new URLSearchParams();
  const active = () => document.body.dataset.role === "admin" && location.hash === "#atividade";

  function invalidate() {
    generation += 1; pending?.abort(); pending = null; exporting = false;
    events.setAttribute("aria-busy", "false");
    more.disabled = true; refresh.disabled = !active(); exportButton.disabled = !active();
  }

  function row(event) {
    const article = document.createElement("article"); article.className = "event-item";
    article.dataset.outcome = event.outcome;
    const copy = document.createElement("div"); copy.className = "event-copy";
    const title = document.createElement("h3"); title.textContent = event.title;
    const detail = document.createElement("p");
    detail.textContent = `${event.actor ? `${event.actor}: ` : ""}${event.detail}`;
    const metadata = document.createElement("details"), summary = document.createElement("summary");
    summary.textContent = `Detalhes do evento #${event.id}`;
    const technical = document.createElement("p");
    technical.textContent = `Tipo: ${event.type} · Origem: ${event.source} · Resultado: ${event.outcome}${event.simulated_at == null ? "" : ` · Tempo virtual: ${event.simulated_at.toFixed(1)} s`}`;
    metadata.append(summary, technical); copy.append(title, detail, metadata);
    const time = document.createElement("time"); time.className = "event-time";
    time.dateTime = event.created_at; time.textContent = new Date(event.created_at).toLocaleString("pt-BR");
    article.append(copy, time); return article;
  }

  async function load(append = false) {
    if (!active() || (append && !cursor)) return;
    invalidate(); const current = generation, controller = new AbortController(); pending = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    const valid = () => current === generation && active();
    const query = new URLSearchParams(applied); query.set("limit", "20");
    if (append) query.set("before_id", cursor);
    else { cursor = null; more.hidden = true; }
    events.setAttribute("aria-busy", "true"); refresh.disabled = true;
    note.textContent = "Consultando eventos…";
    try {
      const response = await fetch(`/api/events?${query}`, { cache: "no-store", signal: controller.signal });
      if (!valid()) return;
      if (response.status === 401) { document.dispatchEvent(new Event("everlock-login-required")); return; }
      if (!response.ok) throw new Error();
      const value = await response.json(); if (!valid()) return;
      if (!append) { events.replaceChildren(); count = 0; }
      events.append(...value.items.map(row)); count += value.items.length;
      if (!count) { const empty = document.createElement("p"); empty.className = "empty-state"; empty.textContent = "Nenhum evento encontrado para estes filtros."; events.append(empty); }
      cursor = value.next_cursor; more.hidden = !value.has_more;
      document.getElementById("event-count").textContent = `${count} eventos exibidos`;
      note.textContent = "Histórico consultado. Use Atualizar para incluir novas ações.";
    } catch { if (valid()) note.textContent = "Não foi possível carregar o histórico. Tente Atualizar novamente."; }
    finally { clearTimeout(timeout); if (valid()) { pending = null; more.disabled = !cursor; refresh.disabled = false; events.setAttribute("aria-busy", "false"); } }
  }

  function resetExport() { exportCursor = null; exportButton.textContent = "Baixar CSV"; }

  function params() {
    const found = new URLSearchParams();
    for (const [name, value] of new FormData(form)) {
      const text = String(value).trim();
      if (text) found.set(name, text);
    }
    return found;
  }

  function validate(found) {
    if (found.get("since") && found.get("until") && found.get("since") > found.get("until")) {
      note.textContent = "A data inicial vem depois da data final.";
      note.dataset.outcome = "error";
      return false;
    }
    note.textContent = "";
    return true;
  }

  function apply(found) {
    applied = found; resetExport(); load();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const found = params();
    if (validate(found)) apply(found);
  });
  document.getElementById("history-clear").addEventListener("click", () => {
    form.reset(); note.textContent = ""; apply(new URLSearchParams());
  });
  form.addEventListener("input", () => {
    resetExport();
    if (exporting) {
      invalidate(); more.disabled = !cursor;
      note.textContent = "Filtros alterados. Baixe o CSV novamente para este recorte.";
    }
  });
  more.addEventListener("click", () => load(true));
  refresh.addEventListener("click", () => load());
  exportButton.addEventListener("click", async () => {
    const found = params();
    if (!validate(found) || !active()) return;
    found.set("limit", "5000");
    if (exportCursor) found.set("before_id", exportCursor);
    invalidate(); const current = generation, controller = new AbortController(); pending = controller;
    exporting = true;
    const timeout = setTimeout(() => controller.abort(), 15000);
    exportButton.disabled = true; note.textContent = "Gerando CSV…";
    const valid = () => current === generation && active();
    try {
      const response = await fetch(`/api/events/export.csv?${found}`, { signal: controller.signal });
      if (!valid()) return;
      if (response.status === 401) { document.dispatchEvent(new Event("everlock-login-required")); return; }
      if (!response.ok) throw new Error();
      const blob = await response.blob(); if (!valid()) return;
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = `everlock-historico-${Date.now()}.csv`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      exportCursor = response.headers.get("X-EverLock-Next-Cursor") || null;
      exportButton.textContent = exportCursor ? "Baixar próxima parte" : "Baixar CSV";
      note.textContent = `${response.headers.get("X-EverLock-Row-Count")} eventos exportados.${exportCursor ? " Há mais registros: baixe a próxima parte ou refine os filtros." : " Exportação concluída para este recorte."}`;
    } catch { if (valid()) note.textContent = "Não foi possível baixar o CSV. Tente novamente."; }
    finally { clearTimeout(timeout); if (valid()) { pending = null; exporting = false; exportButton.disabled = false; more.disabled = !cursor; } }
  });
  function changePage() { invalidate(); if (active()) load(); }
  window.addEventListener("hashchange", changePage);
  document.addEventListener("everlock-session", () => {
    invalidate(); cursor = null; count = 0; events.replaceChildren(); resetExport();
    document.getElementById("event-count").textContent = "—"; note.textContent = ""; changePage();
  });
  document.addEventListener("everlock-login-required", invalidate);
  window.addEventListener("pagehide", invalidate);
})();
