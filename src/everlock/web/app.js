"use strict";

(() => {
  const elements = Object.fromEntries([
    "version", "connection-pill", "connection-label", "connection-warning",
    "door-position", "door-hint", "lock-position", "lock-hint", "last-update",
    "update-hint", "door-scene", "caption-dot", "door-summary", "scene-description",
    "release-description", "action-feedback", "event-count", "events",
  ].map((id) => [id, document.getElementById(id)]));
  const buttons = Array.from(document.querySelectorAll("[data-action]"));
  const clockFormat = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dayFormat = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });
  let lastState = null;
  let connected = false;
  let actionInProgress = false;
  let polling = false;
  let lastEventSignature = "";
  let historyLoaded = false;
  let statusRequestSequence = 0;
  let lastAppliedRequest = 0;

  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(path, {
        cache: "no-store",
        credentials: "same-origin",
        ...options,
        signal: controller.signal,
      });
      const body = await response.json();
      return { response, body };
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function formatTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : clockFormat.format(date);
  }

  function announce(message, outcome = "info") {
    elements["action-feedback"].textContent = message;
    elements["action-feedback"].dataset.outcome = outcome;
  }

  function refreshButtons() {
    for (const button of buttons) {
      let unavailable = !connected || !lastState || actionInProgress;
      if (!unavailable) {
        const door = lastState.door;
        const isOpen = door.position === "open";
        const isReleased = door.lock === "released";
        if (button.dataset.action === "unlock") unavailable = isOpen || isReleased;
        if (button.dataset.action === "end_release") unavailable = !isReleased;
        if (["open", "exit", "key_entry"].includes(button.dataset.action)) unavailable = isOpen;
        if (button.dataset.action === "close") unavailable = !isOpen;
      }
      button.disabled = unavailable;
    }
  }

  function setConnection(isConnected) {
    connected = isConnected;
    document.body.classList.toggle("is-stale", !isConnected);
    elements["connection-pill"].dataset.state = isConnected ? "online" : "offline";
    elements["connection-label"].textContent = isConnected ? "Simulador conectado" : "Sem conexão";
    elements["connection-warning"].hidden = isConnected;
    if (!isConnected) {
      elements["connection-warning"].textContent = lastState
        ? "A conexão com o simulador foi interrompida. O último estado recebido está desatualizado e os controles estão temporariamente indisponíveis."
        : "Não foi possível conectar ao simulador. Os controles serão liberados assim que a conexão estiver disponível.";
      elements["update-hint"].textContent = lastState ? "Último estado recebido · desatualizado" : "Aguardando conexão com o simulador";
      elements["door-hint"].textContent = lastState ? "Informação desatualizada" : "Estado indisponível";
      elements["lock-hint"].textContent = lastState ? "Informação desatualizada" : "Estado indisponível";
      elements["door-summary"].textContent = lastState ? "Última observação · desatualizada" : "Estado da porta indisponível";
      elements["scene-description"].textContent = "A visualização será atualizada quando a conexão voltar.";
    }
    refreshButtons();
  }

  function applyState(state, requestSequence) {
    if (!state || !state.door || !["open", "closed"].includes(state.door.position)) {
      throw new Error("Invalid state");
    }
    if (requestSequence < lastAppliedRequest) return;
    lastAppliedRequest = requestSequence;
    lastState = state;
    const door = state.door;
    const isOpen = door.position === "open";
    const released = door.lock === "released";
    const pending = door.lock === "pending_close";
    const remaining = Math.max(0, Number(door.release_remaining_seconds) || 0);
    const remainingLabel = `${remaining.toFixed(1).replace(".", ",")} s`;

    elements.version.textContent = state.version || "0.1.0";
    elements["door-position"].textContent = isOpen ? "Aberta" : "Fechada";
    elements["door-hint"].textContent = isOpen ? "Feche para concluir o acesso" : "Posição confirmada no simulador";
    elements["lock-position"].textContent = released ? "Liberada" : pending ? "Aguardando" : "Engatada";
    elements["lock-hint"].textContent = released ? `Liberação termina em ${remainingLabel}` : pending ? "É necessário fechar a porta" : "Trava virtual em posição de repouso";
    elements["last-update"].textContent = formatTime(state.observed_at || state.updated_at);
    elements["update-hint"].textContent = "Última observação recebida do simulador";
    elements["door-scene"].dataset.position = door.position;
    elements["door-scene"].dataset.lock = door.lock;
    elements["door-scene"].setAttribute("aria-label", `Porta virtual ${isOpen ? "aberta" : "fechada"}; trava ${released ? "liberada" : pending ? "aguardando fechamento" : "engatada"}.`);
    elements["caption-dot"].dataset.state = isOpen ? "open" : released ? "released" : "closed";
    elements["door-summary"].textContent = isOpen ? "Porta aberta" : released ? "Entrada liberada" : "Porta fechada · trava engatada";
    elements["scene-description"].textContent = isOpen
      ? "A porta precisa ser fechada para concluir o acesso."
      : released ? "Use “Abrir / entrar” antes que a liberação termine." : "Libere a entrada ou experimente o acesso manual.";
    elements["release-description"].textContent = released
      ? `Entrada liberada por mais ${remainingLabel}.`
      : "Liberação temporária da trava virtual.";
    setConnection(true);
  }

  async function updateStatus() {
    const sequence = ++statusRequestSequence;
    try {
      const { response, body } = await request("/api/status");
      if (!response.ok) throw new Error("Status unavailable");
      applyState(body, sequence);
    } catch {
      if (sequence >= lastAppliedRequest) {
        lastAppliedRequest = sequence;
        setConnection(false);
      }
    }
  }

  function createIcon(name) {
    const namespace = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(namespace, "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(namespace, "use");
    use.setAttribute("href", `#icon-${name}`);
    svg.append(use);
    return svg;
  }

  function renderEvents(items) {
    const fragment = document.createDocumentFragment();
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "O histórico começa com a primeira ação. Experimente liberar a entrada.";
      fragment.append(empty);
    }
    for (const event of items) {
      const row = document.createElement("article");
      row.className = "event-item";
      row.dataset.outcome = event.outcome;
      const icon = document.createElement("span");
      icon.className = "event-icon";
      icon.append(createIcon(event.outcome === "denied" ? "info" : event.outcome === "success" ? "check" : "activity"));
      const copy = document.createElement("div");
      copy.className = "event-copy";
      const title = document.createElement("h3");
      title.textContent = event.title;
      const detail = document.createElement("p");
      detail.textContent = event.detail;
      copy.append(title, detail);
      const time = document.createElement("time");
      time.className = "event-time";
      time.dateTime = event.created_at;
      time.textContent = formatTime(event.created_at);
      const date = new Date(event.created_at);
      const day = document.createElement("small");
      day.textContent = Number.isNaN(date.getTime()) ? "" : dayFormat.format(date);
      time.append(day);
      row.append(icon, copy, time);
      fragment.append(row);
    }
    elements.events.replaceChildren(fragment);
  }

  async function updateEvents() {
    try {
      const { response, body } = await request("/api/events?limit=20");
      if (!response.ok || !Array.isArray(body.items)) throw new Error("Events unavailable");
      const signature = JSON.stringify(body.items);
      if (!historyLoaded || signature !== lastEventSignature) {
        renderEvents(body.items);
        lastEventSignature = signature;
      }
      historyLoaded = true;
      elements["event-count"].textContent = body.items.length === 1 ? "1 evento recente" : `${body.items.length} eventos recentes`;
    } catch {
      elements["event-count"].textContent = "Histórico indisponível";
      if (!historyLoaded) {
        elements.events.replaceChildren();
        const message = document.createElement("div");
        message.className = "empty-state";
        message.textContent = "O histórico será exibido quando a conexão estiver disponível.";
        elements.events.append(message);
      }
    } finally {
      elements.events.setAttribute("aria-busy", "false");
    }
  }

  async function performAction(button) {
    if (button.disabled || actionInProgress || !connected) return;
    actionInProgress = true;
    button.classList.add("is-busy");
    button.setAttribute("aria-busy", "true");
    refreshButtons();
    const sequence = ++statusRequestSequence;
    announce("Enviando a ação ao simulador…");
    try {
      const { response, body } = await request("/api/actions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: button.dataset.action }),
      });
      if (body.state) applyState(body.state, sequence);
      if (response.ok && body.ok) {
        announce(body.message || "Ação concluída no simulador.", "success");
      } else if (response.status === 409) {
        announce(body.message || "A ação não pode ser realizada no estado atual.", "denied");
      } else {
        announce("A ação não foi confirmada. Confira o estado da porta antes de tentar novamente.", "error");
      }
    } catch {
      if (sequence >= lastAppliedRequest) {
        lastAppliedRequest = sequence;
        setConnection(false);
      }
      announce("Não foi possível confirmar a ação. Ela não será reenviada automaticamente.", "error");
    } finally {
      actionInProgress = false;
      button.classList.remove("is-busy");
      button.removeAttribute("aria-busy");
      refreshButtons();
      await Promise.allSettled([updateStatus(), updateEvents()]);
    }
  }

  async function poll() {
    if (polling || actionInProgress) return;
    polling = true;
    try {
      await Promise.allSettled([updateStatus(), updateEvents()]);
    } finally {
      polling = false;
    }
  }

  for (const button of buttons) button.addEventListener("click", () => performAction(button));
  for (const link of document.querySelectorAll(".nav-link")) {
    link.addEventListener("click", () => {
      for (const item of document.querySelectorAll(".nav-link")) {
        item.classList.toggle("active", item === link);
        if (item === link) item.setAttribute("aria-current", "location");
        else item.removeAttribute("aria-current");
      }
    });
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) poll();
  });
  poll();
  window.setInterval(() => {
    if (!document.hidden) poll();
  }, 1000);
})();
