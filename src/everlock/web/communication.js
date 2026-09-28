"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const labels = { requested: "Solicitado", accepted: "Recebido", executed: "Executado", failed: "Falhou", expired: "Expirado" };
  const locks = { engaged: "trava engatada", released: "trava liberada", pending_close: "trava aguardando fechamento" };
  const time = (seconds) => new Date(seconds * 1000).toLocaleTimeString("pt-BR");
  let generation = 0, sequence = 0, applied = 0;
  let snapshot = null, lastPayload = null, busy = false, loading = false, configured = false;
  let duplicate = false, trackCommand = false;
  const signedIn = () => Boolean(document.body.dataset.role);
  const feedback = (message) => { byId("command-feedback").textContent = message; };
  const commandFeedback = (command) => feedback(`${duplicate ? "Envio repetido; sem nova atuação. " : ""}${command.status === "requested" ? "" : `${labels[command.status]}. `}${command.message}`);

  async function request(path, body) {
    const session = generation;
    const response = await fetch(`/api/${path}`, {
      method: body ? "POST" : "GET", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(5000),
    });
    const value = await response.json();
    if (session !== generation) throw new Error("Sessão alterada.");
    if (response.status === 401) document.dispatchEvent(new Event("everlock-login-required"));
    if (!response.ok && !value.command) {
      throw new Error(typeof value.detail === "string" ? value.detail : "Não foi possível concluir a solicitação.");
    }
    return value;
  }

  function controls() {
    const available = signedIn() && !busy && snapshot?.channel_available && !snapshot.observation_stale;
    const closed = snapshot?.observation?.door.position === "closed";
    byId("remote-unlock").disabled = !available || !closed;
    byId("remote-lock").disabled = !available || !closed;
    byId("apply-network").disabled = !signedIn() || busy;
    byId("repeat-command").disabled = !signedIn() || busy || !lastPayload;
  }

  function render(value) {
    snapshot = value;
    byId("network-internet").textContent = value.internet_available ? "Disponível" : "Cortada";
    byId("network-lan").textContent = value.lan_available ? "Disponível" : "Cortada";
    byId("network-device").textContent = value.device_available ? "Ligado" : "Sem operação";
    byId("remote-observation").dataset.stale = String(value.observation_stale);
    const door = value.observation?.door;
    byId("remote-door").textContent = door
      ? `${value.observation_stale ? "Última leitura: " : "Leitura recebida: "}${door.position === "open" ? "porta aberta" : "porta fechada"}, ${locks[door.lock]}.`
      : "Sem leitura do dispositivo.";
    byId("remote-reading-age").textContent = value.observation
      ? `${value.observation_stale ? "Informação antiga; não confirma o estado atual. " : ""}Recebida às ${new Date(value.observation.observed_at).toLocaleTimeString("pt-BR")} · há ${Math.floor(value.observation_age_seconds)} s.`
      : "Aguardando uma conexão disponível.";
    byId("remote-channel").textContent = value.reason;
    if (!configured) {
      const fields = byId("network-form").elements;
      fields.internet_available.checked = value.internet_available;
      fields.lan_available.checked = value.lan_available;
      // A API aceita qualquer atraso entre 0 e 30, inclusive os configurados fora da tela.
      const delay = String(value.delay_seconds);
      if (![...fields.delay_seconds.options].some((option) => option.value === delay)) {
        fields.delay_seconds.add(new Option(`${delay} segundos`, delay));
      }
      fields.delay_seconds.value = delay;
      configured = true;
    }
    const rows = value.commands.map((command) => {
      const row = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = `${command.action === "unlock" ? "Liberar" : "Travar"} · ${labels[command.status]} · ${time(command.requested_at)}`;
      const message = document.createElement("p"); message.textContent = command.message;
      const trail = document.createElement("p");
      trail.textContent = command.transitions.map((item) => `${labels[item.status]} ${time(item.occurred_at)}`).join(" → ");
      const detail = document.createElement("small");
      detail.textContent = `${command.actor} · prazo de ${command.valid_for_seconds} s reais · ID ${command.id}`;
      row.append(title, message, trail, detail);
      return row;
    });
    if (!rows.length) { const empty = document.createElement("li"); empty.textContent = "Nenhum comando enviado."; rows.push(empty); }
    byId("command-history").replaceChildren(...rows);
    const latest = value.commands.find((command) => command.id === lastPayload?.command_id);
    if (trackCommand && latest) commandFeedback(latest);
    controls();
  }

  function disconnected() {
    if (snapshot) snapshot.observation_stale = true;
    byId("remote-observation").dataset.stale = "true";
    byId("remote-reading-age").textContent = "Sem atualização do servidor. A leitura anterior não confirma o estado atual.";
    byId("remote-channel").textContent = "Verifique se o servidor está aberto. Nenhum comando será reenviado automaticamente.";
    for (const id of ["network-internet", "network-lan", "network-device"]) byId(id).textContent = "Sem atualização";
    controls();
  }

  async function refresh() {
    if (!signedIn() || loading || busy) return;
    const session = generation, order = ++sequence;
    loading = true;
    try {
      const value = await request("communication");
      if (session === generation && order >= applied) { applied = order; render(value); }
    } catch {
      if (session === generation && order >= applied) { applied = order; disconnected(); }
    } finally { if (session === generation) loading = false; }
  }

  async function change(path, payload) {
    if (busy || !signedIn()) return;
    const session = generation, order = ++sequence;
    applied = order; busy = true; controls();
    try {
      const value = await request(path, payload);
      if (session !== generation) return;
      if (value.command) { duplicate = value.duplicate; trackCommand = true; commandFeedback(value.command); }
      else { trackCommand = false; configured = false; render(value); feedback("Cenário de rede atualizado."); }
    } catch (error) {
      if (session === generation) {
        feedback(`${error.message} Consulte o histórico antes de enviar outro comando; o envio anterior pode ter chegado ao servidor.`);
        disconnected();
      }
    } finally {
      if (session === generation) { busy = false; controls(); await refresh(); }
    }
  }

  for (const action of ["unlock", "lock"]) {
    byId(`remote-${action}`).addEventListener("click", () => {
      if (!snapshot?.observation || snapshot.observation_stale || busy) return;
      lastPayload = { command_id: crypto.randomUUID(), action,
        expected_version: snapshot.observation.door.version,
        valid_for_seconds: Number(byId("command-ttl").value) };
      duplicate = false; trackCommand = true;
      feedback("Enviando solicitação. Aguarde a confirmação no histórico.");
      change("commands", lastPayload);
    });
  }
  byId("repeat-command").addEventListener("click", () => { if (lastPayload) change("commands", lastPayload); });
  byId("network-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const fields = event.target.elements;
    change("simulation/network", { internet_available: fields.internet_available.checked,
      lan_available: fields.lan_available.checked, delay_seconds: Number(fields.delay_seconds.value) });
  });
  document.addEventListener("everlock-session", () => {
    generation += 1; snapshot = lastPayload = null;
    busy = loading = configured = duplicate = trackCommand = false;
    feedback(""); byId("command-history").replaceChildren();
    byId("remote-door").textContent = "Aguardando leitura do dispositivo.";
    disconnected(); refresh();
  });
  setInterval(refresh, 1000);
})();
