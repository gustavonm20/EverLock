"use strict";

(() => {
  const key = "everlock.theme";
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  let choice = null;
  try {
    const saved = localStorage.getItem(key);
    if (saved === "light" || saved === "dark") choice = saved;
  } catch { /* O tema continua funcionando quando o armazenamento está bloqueado. */ }

  function apply() {
    const dark = choice ? choice === "dark" : system.matches;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    const button = document.getElementById("theme-toggle");
    if (button) {
      const label = dark ? "Ativar tema claro" : "Ativar tema escuro";
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
      button.setAttribute("aria-pressed", String(dark));
    }
  }
  // Executado antes do CSS para evitar um clarão ao abrir no tema escuro.
  apply();
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    document.getElementById("theme-toggle").addEventListener("click", () => {
      choice = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem(key, choice); } catch { /* Preferência válida nesta aba. */ }
      apply();
    });
  });
  system.addEventListener("change", () => { if (!choice) apply(); });
  window.addEventListener("storage", (event) => {
    if (event.key === key || event.key === null) {
      choice = event.newValue === "light" || event.newValue === "dark" ? event.newValue : null;
      apply();
    }
  });
})();
