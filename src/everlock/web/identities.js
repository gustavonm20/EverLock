"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const dayNames = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
  const stateLabels = {
    ready: "Pronta para testes", not_enrolled: "Sem cadastro simulado",
    inactive: "Desativada", revoked: "Consentimento revogado",
  };
  const isAdmin = () => document.body.dataset.role === "admin";
  let generation = 0, busy = false, policy = null, signature = "";

  const dateText = (seconds) => new Date(seconds * 1000).toLocaleDateString("pt-BR");
  const feedback = (text, outcome = "info") => {
    byId("identity-message").textContent = text;
    byId("identity-message").dataset.outcome = outcome;
  };

  function errorText(value) {
    if (Array.isArray(value.detail)) {
      return value.detail.map((item) => item.msg.replace(/^Value error, /, "")).join(" ");
    }
    return typeof value.detail === "string" ? value.detail : (value.message || "Confira os campos informados.");
  }

  async function api(path, method = "GET", body) {
    const session = generation;
    const response = await fetch(`/api/${path}`, {
      method, credentials: "same-origin", cache: "no-store",
      // O servidor exige application/json em toda alteração, mesmo sem corpo.
      headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(8000),
    });
    const value = await response.json();
    if (session !== generation) throw new Error("Sessão alterada.");
    if (response.status === 401) document.dispatchEvent(new Event("everlock-login-required"));
    // Um teste de reconhecimento recusado é um resultado válido, não uma falha de rede.
    if (!response.ok && !value.simulated) throw new Error(errorText(value));
    return { ok: response.ok, value };
  }

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function actionButton(text, handler, className = "button button-quiet") {
    const node = element("button", text, className);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  async function perform(work, success) {
    if (busy) return;
    busy = true;
    byId("identity-list").setAttribute("aria-busy", "true");
    for (const control of document.querySelectorAll("#identidades button")) control.disabled = true;
    try {
      const result = await work();
      // Sem mensagem própria: a ação já informou o resultado (ex.: teste recusado).
      if (success !== null) feedback(typeof success === "function" ? success(result) : success, "success");
    } catch (error) {
      feedback(error.message, "error");
    } finally {
      busy = false;
      await load(true);
      for (const control of document.querySelectorAll("#identidades button")) control.disabled = false;
    }
  }

  async function simulate(body) {
    const { ok, value } = await api("recognition/simulate", "POST", body);
    feedback(`Teste simulado. ${value.message}`, ok ? "success" : "denied");
    return value;
  }

  function scheduleText(schedule) {
    const days = schedule.days.length === 7 ? "todos os dias" : schedule.days.map((day) => dayNames[day]).join(", ");
    return `${days}, das ${schedule.start} às ${schedule.end}`;
  }

  function renderItem(item) {
    const card = element("article", undefined, "identity-row");
    const head = element("header");
    const state = element("span", stateLabels[item.state], "identity-state");
    state.dataset.state = item.state;
    head.append(element("h4", `#${item.id} · ${item.label}`), state);
    const consent = item.consent.revoked_at === null
      ? `Consentimento ${item.consent.version} registrado por ${item.consent.recorded_by} em ${dateText(item.consent.granted_at)}. Exclusão automática em ${dateText(item.expires_at)}.`
      : `Consentimento revogado em ${dateText(item.consent.revoked_at)}. O cadastro foi apagado; exclua a identidade ou cadastre-a de novo.`;
    card.append(
      head,
      element("p", `Horário permitido: ${scheduleText(item.schedule)}.`),
      element("p", consent),
      element("p", `Agora: ${item.access_now.message}`),
    );
    if (item.face_samples) card.append(element("p", `Cadastro facial: ${item.face_samples} amostras (somente vetores cifrados; nenhuma imagem guardada).`));
    const actions = element("div", undefined, "identity-actions");
    const target = `identities/${item.id}`;
    if (item.enrollment !== "none") {
      actions.append(actionButton("Simular reconhecimento", () => perform(
        () => simulate({ scenario: "match", identity_id: item.id }), null,
      ), "button button-primary"));
      actions.append(actionButton("Remover cadastro", () => perform(
        () => api(`${target}/enrollment`, "DELETE"), "Cadastro simulado removido.",
      )));
    }
    if (item.state !== "revoked") {
      actions.append(actionButton(item.face_samples ? "Refazer cadastro facial" : "Cadastrar rosto (câmera)", () => {
        if (!item.face_consent_ok) { feedback("Esta identidade aceitou um termo antigo. Exclua-a e cadastre de novo para usar o rosto.", "error"); return; }
        document.dispatchEvent(new CustomEvent("everlock-face-enroll", { detail: { id: item.id } }));
      }, item.enrollment === "none" ? "button button-primary" : "button button-quiet"));
    }
    if (item.enrollment === "none" && item.state !== "revoked") {
      actions.append(actionButton("Registrar cadastro simulado", () => perform(
        () => api(`${target}/enrollment`, "POST"), "Cadastro simulado registrado. Nenhuma imagem foi coletada.",
      ), "button button-secondary"));
    }
    if (item.state !== "revoked") {
      actions.append(actionButton(item.active ? "Desativar" : "Ativar", () => perform(
        () => api(target, "PATCH", { active: !item.active }), item.active ? "Identidade desativada." : "Identidade ativada.",
      )));
      actions.append(actionButton("Revogar consentimento", () => {
        if (!window.confirm("Revogar o consentimento apaga o cadastro simulado e bloqueia novos testes. Continuar?")) return;
        perform(() => api(`${target}/consent/revoke`, "POST"), "Consentimento revogado e cadastro apagado.");
      }));
    }
    actions.append(actionButton("Excluir identidade", () => {
      if (!window.confirm("Excluir remove o apelido, o consentimento, o cadastro e os horários. Continuar?")) return;
      perform(() => api(target, "DELETE"), "Identidade excluída por completo.");
    }, "button button-danger"));
    card.append(actions);
    return card;
  }

  // Painel "Reconhecimento facial" da tela principal: só identidades prontas para teste.
  function renderFaceEntry(items) {
    const select = byId("face-identity"), button = byId("face-release");
    const previous = select.value;
    const ready = items.filter((item) => item.state === "ready");
    select.replaceChildren(...(ready.length
      ? ready.map((item) => { const option = element("option", `#${item.id} · ${item.label}`); option.value = String(item.id); return option; })
      : [element("option", "Nenhuma identidade pronta")]));
    if (ready.some((item) => String(item.id) === previous)) select.value = previous;
    select.disabled = button.disabled = !ready.length;
  }

  byId("face-release").addEventListener("click", async () => {
    const button = byId("face-release"), result = byId("face-result");
    const identityId = Number(byId("face-identity").value);
    if (!identityId || busy) return;
    button.disabled = true;
    try {
      const { ok, value } = await api("recognition/simulate", "POST", { scenario: "match", identity_id: identityId });
      result.textContent = `Teste simulado. ${value.message}`;
      result.dataset.outcome = ok ? "success" : "denied";
    } catch (error) {
      result.textContent = error.message;
      result.dataset.outcome = "denied";
    } finally {
      button.disabled = false;
      await load(true);
    }
  });

  function render(items, events) {
    renderFaceEntry(items);
    const list = byId("identity-list");
    if (!items.length) {
      list.replaceChildren(element("p", "Nenhuma identidade cadastrada.", "empty-state"));
    } else {
      list.replaceChildren(...items.map(renderItem));
    }
    byId("identity-history").replaceChildren(...events.map((item) => element(
      "li", `${new Date(item.created_at).toLocaleString("pt-BR")} · ${item.actor || "Sistema"}: ${item.detail}`,
    )));
    list.setAttribute("aria-busy", "false");
  }

  async function loadPolicy() {
    if (policy) return;
    const { value } = await api("identities/policy");
    policy = value;
    byId("consent-version").textContent = `(versão ${value.version})`;
    byId("consent-text").textContent = value.text;
    const retention = byId("identity-retention");
    retention.min = value.retention.min_days;
    retention.max = value.retention.max_days;
    retention.value = value.retention.default_days;
  }

  async function load(force = false) {
    if (!isAdmin() || (busy && !force)) return;
    const session = generation;
    try {
      await loadPolicy();
      const [{ value: list }, { value: events }] = await Promise.all([api("identities"), api("identities/events")]);
      if (session !== generation) return;
      const next = JSON.stringify([list.items, events.items]);
      if (next !== signature || force) {
        signature = next;
        render(list.items, events.items);
      }
    } catch {
      if (session === generation && !signature) {
        byId("identity-list").replaceChildren(element("p", "As identidades serão exibidas quando a conexão estiver disponível.", "empty-state"));
      }
    }
  }

  function windowChoice() {
    const choice = byId("identity-window").value;
    if (choice === "always") return { days: [0, 1, 2, 3, 4, 5, 6], start: "00:00", end: "24:00" };
    if (choice === "business") return { days: [0, 1, 2, 3, 4], start: "08:00", end: "18:00" };
    const form = byId("identity-form");
    const days = Array.from(form.querySelectorAll("input[name=day]:checked"), (box) => Number(box.value));
    return { days, start: form.elements.start.value, end: form.elements.end.value };
  }

  byId("identity-window").addEventListener("change", () => {
    byId("identity-custom").hidden = byId("identity-window").value !== "custom";
  });

  byId("identity-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const schedule = windowChoice();
    if (!schedule.days.length) { feedback("Escolha ao menos um dia da semana.", "error"); return; }
    if (!schedule.start || !schedule.end) { feedback("Informe o início e o fim da janela.", "error"); return; }
    if (!form.reportValidity() || !policy) return;
    await perform(async () => {
      const created = (await api("identities", "POST", {
        label: form.elements.label.value,
        retention_days: Number(form.elements.retention_days.value),
        consent: form.elements.consent.checked,
        consent_version: policy.version,
        ...schedule,
      })).value;
      form.reset();
      byId("identity-custom").hidden = true;
      return created;
    }, (created) => `Identidade #${created.id} cadastrada, ainda sem cadastro. Use “Cadastrar rosto (câmera)” ou o cadastro simulado.`);
  });

  byId("simulate-unknown").addEventListener("click", () => perform(
    () => simulate({ scenario: "no_match" }), null,
  ));

  function reset() {
    generation += 1;
    busy = false; policy = null; signature = "";
    byId("identity-form").reset();
    byId("identity-custom").hidden = true;
    byId("identity-list").replaceChildren();
    byId("identity-history").replaceChildren();
    feedback("Cadastre uma identidade para começar. Nenhum dado biométrico será guardado.");
    load();
  }

  document.addEventListener("everlock-identities-changed", () => load(true));
  document.addEventListener("everlock-identities-changed", () => load(true));
  document.addEventListener("everlock-session", reset);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  window.setInterval(() => { if (!document.hidden) load(); }, 10000);
})();
