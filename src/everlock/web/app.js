"use strict";

(() => {
  const elements = Object.fromEntries([
    "version", "connection-pill", "connection-label", "connection-warning",
    "door-position", "door-hint", "lock-position", "lock-hint", "last-update",
    "update-hint", "door-scene", "caption-dot", "door-summary", "scene-description",
    "release-description", "action-feedback", "event-count", "events",
    "battery-percent", "battery-meter", "battery-detail", "mains-state", "device-state",
    "power-profile", "battery-runtime", "power-notice", "virtual-time", "clock-state",
    "clock-speed", "toggle-clock", "cut-power", "restore-power", "power-feedback",
  ].map((id) => [id, document.getElementById(id)]));
  const buttons = Array.from(document.querySelectorAll("[data-action]"));
  const labControls = Array.from(document.querySelectorAll("#energia button, #energia input, #energia select"));
  const configForm = document.getElementById("power-config-form");
  const numberFormat = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
  let configLoaded = false;
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

  function announce(message, outcome = "info", target = "action-feedback") {
    elements[target].textContent = message;
    elements[target].dataset.outcome = outcome;
  }

  function duration(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    return `${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m ${String(total % 60).padStart(2, "0")}s`;
  }

  function updatePower(state) {
    const power = state.power;
    const battery = power.battery;
    const clock = state.simulation;
    const labels = { normal: "Normal", low: "Baixa", critical: "Crítica", empty: "Esgotada" };
    const profiles = { normal: "Normal", economy: "Econômico", off: "Residual" };
    const off = state.device.status === "powered_off";
    const recovering = state.device.status === "recovering";
    elements["battery-percent"].textContent = `${numberFormat.format(battery.percent)}%`;
    elements["battery-meter"].value = battery.percent;
    elements["battery-meter"].dataset.level = battery.level;
    const flow = battery.charging ? "Carregando" : battery.flow_w < 0 ? "Consumindo" : "Sem consumo da bateria";
    elements["battery-detail"].textContent = `${numberFormat.format(battery.stored_wh)} / ${numberFormat.format(battery.capacity_wh)} Wh · ${labels[battery.level]} · ${flow}`;
    elements["mains-state"].textContent = power.mains_available ? "Disponível" : "Cortada";
    elements["device-state"].textContent = off ? "Desligado" : recovering ? "Reiniciando" : "Ligado";
    elements["power-profile"].textContent = `${profiles[power.profile]} · ${numberFormat.format(power.load_w)} W`;
    elements["battery-runtime"].textContent = duration(battery.runtime_seconds);
    elements["power-notice"].dataset.state = state.device.status;
    elements["power-notice"].textContent = off
      ? "Dispositivo virtual desligado. Saída interna, chave e fechamento manuais continuam disponíveis. Restaure a alimentação para retomar."
      : recovering ? `Recuperando por mais ${numberFormat.format(state.device.recovery_remaining_seconds)} segundos virtuais. ${clock.paused ? "Retome ou avance o tempo." : "Aguarde a inicialização."} A trava não será liberada.`
      : power.mains_available
        ? "A autonomia estima uma queda agora, sem novas liberações. A alimentação externa sustenta o dispositivo e a recarga."
        : "Operando na bateria virtual. O modo econômico começa em 20%; o desligamento ocorre em 5%.";
    elements["virtual-time"].textContent = duration(clock.elapsed_seconds);
    elements["clock-state"].textContent = `${clock.paused ? "Pausado" : "Em andamento"} · velocidade ${clock.speed}×`;
    elements["clock-speed"].value = String(clock.speed);
    elements["toggle-clock"].textContent = clock.paused ? "Retomar tempo" : "Pausar tempo";
    if (!configLoaded) {
      for (const [name, value] of Object.entries(power.config)) {
        const input = configForm.elements.namedItem(name === "efficiency" ? "efficiency_percent" : name);
        if (input) input.value = name === "efficiency" ? value * 100 : value;
      }
      configForm.elements.namedItem("initial_percent").value = Math.round(battery.percent * 10) / 10;
      configLoaded = true;
    }
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
        if (lastState.device.status !== "online" && ["unlock", "open", "end_release"].includes(button.dataset.action)) unavailable = true;
      }
      button.disabled = unavailable;
    }
    for (const control of labControls) {
      let unavailable = !connected || !lastState || actionInProgress;
      if (!unavailable) {
        if (control.id === "cut-power") unavailable = !lastState.power.mains_available;
        if (control.id === "restore-power") unavailable = lastState.power.mains_available;
        if (control.dataset.step) unavailable = !lastState.simulation.paused;
      }
      control.disabled = unavailable;
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
      elements["power-notice"].textContent = "Sem conexão com o laboratório. As leituras de energia exibidas podem estar desatualizadas.";
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

    elements.version.textContent = state.version || "0.2.0";
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
    elements["release-description"].textContent = state.device.status !== "online"
      ? "Dispositivo virtual indisponível; acesso manual disponível."
      : released ? `Entrada liberada por mais ${remainingLabel} virtuais${state.simulation.paused ? " (tempo pausado)" : ""}.`
        : "Liberação de 3 segundos no relógio virtual.";
    updatePower(state);
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
      if (typeof event.simulated_at === "number") {
        const virtual = document.createElement("small");
        virtual.textContent = `Virtual: ${duration(event.simulated_at)}`;
        time.append(virtual);
      }
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

  async function performAction(button, path = "/api/actions", payload = { action: button.dataset.action }, feedback = "action-feedback") {
    if (button.disabled || actionInProgress || !connected) return;
    actionInProgress = true;
    button.classList.add("is-busy");
    button.setAttribute("aria-busy", "true");
    refreshButtons();
    const sequence = ++statusRequestSequence;
    announce("Enviando a ação ao simulador…", "info", feedback);
    try {
      const { response, body } = await request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (body.state) applyState(body.state, sequence);
      if (response.ok && body.ok) {
        announce(body.message || "Ação concluída no simulador.", "success", feedback);
      } else if (response.status === 409) {
        announce(body.message || "A ação não pode ser realizada no estado atual.", "denied", feedback);
      } else if (response.status === 422) {
        const detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join(" ") : "Revise os valores informados.";
        announce(`Confira os parâmetros: ${detail}`, "error", feedback);
      } else {
        announce("A ação não foi confirmada. Confira o estado antes de tentar novamente.", "error", feedback);
      }
    } catch {
      if (sequence >= lastAppliedRequest) {
        lastAppliedRequest = sequence;
        setConnection(false);
      }
      announce("Não foi possível confirmar a ação. Ela não será reenviada automaticamente.", "error", feedback);
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
  const labAction = (button, route, payload) => performAction(button, `/api/simulation/${route}`, payload, "power-feedback");
  elements["cut-power"].addEventListener("click", () => labAction(elements["cut-power"], "power", { mains_available: false }));
  elements["restore-power"].addEventListener("click", () => labAction(elements["restore-power"], "power", { mains_available: true }));
  elements["toggle-clock"].addEventListener("click", () => labAction(elements["toggle-clock"], "clock", { paused: !lastState.simulation.paused }));
  elements["clock-speed"].addEventListener("change", () => labAction(elements["clock-speed"], "clock", { speed: Number(elements["clock-speed"].value) }));
  for (const button of document.querySelectorAll("[data-step]")) {
    button.addEventListener("click", () => labAction(button, "clock", { advance_seconds: Number(button.dataset.step) }));
  }
  configForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!connected || actionInProgress || !configForm.reportValidity()) return;
    const payload = Object.fromEntries(Array.from(new FormData(configForm), ([key, value]) => [key, Number(value)]));
    payload.efficiency = payload.efficiency_percent / 100;
    delete payload.efficiency_percent;
    labAction(document.getElementById("apply-power-config"), "power/config", payload);
  });
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
