"use strict";

// Filtros do histórico (página Atividade) e download em CSV. Só administradores chegam aqui.
(() => {
  const form = document.getElementById("history-filter");
  const events = document.getElementById("events");
  const note = document.getElementById("history-note");

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
    events.dataset.query = found.toString() ? `&${found}` : "";
    document.dispatchEvent(new Event("everlock-history-filter"));
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const found = params();
    if (validate(found)) apply(found);
  });
  document.getElementById("history-clear").addEventListener("click", () => {
    form.reset(); note.textContent = ""; apply(new URLSearchParams());
  });
  document.getElementById("history-export").addEventListener("click", () => {
    const found = params();
    if (!validate(found)) return;
    found.set("limit", "5000");
    note.textContent = "Gerando o arquivo CSV (até 5.000 eventos, separado por ponto e vírgula).";
    note.dataset.outcome = "info";
    window.location.assign(`/api/events/export.csv?${found}`);
  });
})();
