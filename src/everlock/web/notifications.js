"use strict";

// Painel de notificações por webhook (n8n) na página Atividade. Só administradores.
(() => {
  const byId = (id) => document.getElementById(id);
  const { request, messageOf, pause } = window.FaceKit;
  let timer = null;

  const when = (iso) => new Date(iso).toLocaleString("pt-BR");

  function describe(status) {
    if (!status.configured) {
      return status.reason
        ? `Desativadas: ${status.reason}`
        : "Desativadas. Para enviar alertas ao n8n, configure EVERLOCK_WEBHOOK_URL em everlock.env (veja docs/notifications.md).";
    }
    const parts = [`Ativas para ${status.destination}, nível “${status.level}”, ${status.signed ? "com assinatura" : "SEM assinatura (defina EVERLOCK_WEBHOOK_SECRET)"}.`];
    if (status.insecure_transport) parts.push("Atenção: o destino usa http fora desta rede; prefira https.");
    parts.push(`Enviadas: ${status.sent}; falhas: ${status.failed}; na fila: ${status.queued}${status.dropped ? `; descartadas: ${status.dropped}` : ""}.`);
    if (status.last_ok_at) parts.push(`Último envio com sucesso: ${when(status.last_ok_at)}.`);
    if (status.last_error) parts.push(`Último erro: ${status.last_error}`);
    return parts.join(" ");
  }

  async function load() {
    if (document.body.dataset.role !== "admin") return;
    try {
      const { ok, value } = await request("notifications/status");
      if (ok) {
        byId("notify-status").textContent = describe(value);
        byId("notify-test").disabled = !value.configured;
      }
    } catch { /* mantém o último estado */ }
  }

  byId("notify-test").addEventListener("click", async () => {
    const button = byId("notify-test"), note = byId("notify-message");
    button.disabled = true;
    try {
      const { ok, value } = await request("notifications/test", "POST", {});
      note.textContent = ok ? value.message : messageOf(value, "Não foi possível enviar o teste.");
      note.dataset.outcome = ok ? "success" : "error";
      await pause(1500);
    } catch { note.textContent = "Falha ao falar com o servidor local."; note.dataset.outcome = "error"; }
    await load();
  });

  const start = () => { window.clearInterval(timer); load(); timer = window.setInterval(() => { if (!document.hidden) load(); }, 15000); };
  document.addEventListener("everlock-session", start);
})();
