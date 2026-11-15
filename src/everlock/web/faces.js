"use strict";

// Câmera do navegador para o reconhecimento facial. As fotos viram JPEG em memória, são enviadas
// ao servidor local e nunca são salvas: nem aqui, nem lá. Só admins usam estes recursos.
(() => {
  const byId = (id) => document.getElementById(id);
  const SHOTS = 5;
  const prompts = [
    "Olhe de frente para a câmera.", "Continue de frente, relaxado.",
    "Vire o rosto bem pouco para a esquerda.", "Vire o rosto bem pouco para a direita.",
    "Volte a olhar de frente. Última foto!",
  ];
  const { start: startCamera, stop: stopCamera, capture, captureProgress, pause, isOn, request: api } = window.FaceKit;
  const progress = byId("face-enroll-progress");
  let status = { available: false, reason: "Verificando…" };
  let enrollingId = null, busy = false, generation = 0, sessionGeneration = 0;
  let cameraStarting = false, activeChallenge = null;
  let enrollmentPolicy = null, returnFocus = null;

  const isAdmin = () => document.body.dataset.role === "admin";

  function cancelChallenge(id) {
    if (!id) return;
    // keepalive permite encerrar o desafio também quando a página está sendo fechada.
    fetch(`/api/recognition/challenge/${encodeURIComponent(id)}`, {
      method: "DELETE", credentials: "same-origin", keepalive: true,
      headers: { "Content-Type": "application/json" },
    }).catch(() => {});
  }

  function stopAll() {
    generation += 1;
    cancelChallenge(activeChallenge); activeChallenge = null;
    for (const video of [byId("face-enroll-video"), byId("face-verify-video")]) stopCamera(video);
    byId("face-camera-toggle").textContent = "Ligar câmera";
    byId("face-verify").disabled = true;
    byId("face-enroll-panel").hidden = true; enrollingId = null; busy = false;
    enrollmentPolicy = null; byId("face-subject-consent").checked = false;
    byId("face-enroll-prepare").disabled = true;
    byId("face-enroll-start").disabled = true;
    captureProgress(progress);
  }

  // --- estado do motor facial ---------------------------------------------------------------
  async function loadStatus() {
    if (!isAdmin()) return;
    const session = sessionGeneration;
    try {
      const { ok, value } = await api("faces/status");
      if (!ok || session !== sessionGeneration || !isAdmin()) return;
      status = value;
    } catch { return; }
    const title = byId("face-entry-title"), text = byId("face-entry-text");
    byId("face-live").hidden = !status.available;
    renderEngine();
    if (status.available) {
      title.textContent = "Reconhecimento facial por câmera";
      text.textContent = status.test_double
        ? "Atenção: esta instância usa um motor de testes automatizados. O uso normal carrega o pipeline OpenCV local."
        : `Modelos ${status.model}. A câmera pede um giro curto do rosto antes de comparar. As imagens são analisadas na memória e descartadas; liberar não abre a porta.`;
    } else {
      title.textContent = "Reconhecimento por câmera indisponível";
      text.textContent = `${status.reason} Sem o motor, a porta não libera por rosto (falha fechada). O acesso manual continua disponível.`;
    }
  }

  // --- cadastro facial ----------------------------------------------------------------------
  const step = (text, outcome = "info") => { byId("face-enroll-step").textContent = text; byId("face-enroll-step").dataset.outcome = outcome; };

  document.addEventListener("everlock-face-enroll", (event) => {
    if (!isAdmin() || busy || cameraStarting) return;
    stopAll();
    returnFocus = document.activeElement;
    const panel = byId("face-enroll-panel");
    panel.hidden = false; enrollingId = event.detail.id;
    byId("face-enroll-title").textContent = `Cadastro facial da identidade #${enrollingId}`;
    enrollmentPolicy = event.detail;
    byId("face-enroll-start").disabled = true;
    byId("face-subject-text").textContent = event.detail.text;
    byId("face-subject-retention").textContent = `Prazo escolhido: ${event.detail.retention} dias. Exclusão prevista: ${new Date(event.detail.expiresAt * 1000).toLocaleString("pt-BR")}. O aceite não renova esse prazo.`;
    panel.scrollIntoView({ block: "nearest" });
    if (!status.available) { step(`${status.reason}`, "error"); return; }
    step("1 de 3 · Leia o termo com a pessoa. A câmera ainda está desligada.");
    byId("face-subject-consent").focus({ preventScroll: true });
  });

  byId("face-subject-consent").addEventListener("change", () => {
    if (!byId("face-subject-consent").checked && (cameraStarting || isOn(byId("face-enroll-video")))) { stopAll(); return; }
    byId("face-enroll-prepare").disabled = !byId("face-subject-consent").checked || !status.available || cameraStarting;
  });
  byId("face-enroll-prepare").addEventListener("click", async () => {
    if (!isAdmin() || busy || !enrollmentPolicy || cameraStarting || isOn(byId("face-enroll-video")) || !byId("face-subject-consent").checked) return;
    const session = generation;
    cameraStarting = true; byId("face-enroll-start").disabled = true;
    byId("face-enroll-prepare").disabled = true;
    try {
      const consent = await api(`identities/${enrollingId}/consent/confirm`, "POST", { accepted: true, version: enrollmentPolicy.version });
      if (session !== generation) return;
      if (!consent.ok) throw new Error(typeof consent.value.detail === "string" ? consent.value.detail : "Não foi possível registrar o aceite.");
      await startCamera(byId("face-enroll-video"));
      if (session !== generation) { stopCamera(byId("face-enroll-video")); return; }
      step("2 de 3 · Câmera ligada. Use boa iluminação, fique sozinho no enquadramento e centralize o rosto. Inicie quando estiver pronto.");
      captureProgress(progress, 0);
      byId("face-enroll-start").disabled = false;
      byId("face-enroll-start").focus();
    } catch (error) {
      if (session === generation) { step(error.message, "error"); byId("face-enroll-start").disabled = true; }
    } finally {
      cameraStarting = false;
      if (session === generation) byId("face-enroll-prepare").disabled = !byId("face-subject-consent").checked || isOn(byId("face-enroll-video"));
    }
  });

  byId("face-enroll-start").addEventListener("click", async () => {
    if (!isAdmin() || busy || enrollingId === null || !isOn(byId("face-enroll-video"))) return;
    busy = true; byId("face-enroll-start").disabled = true;
    const video = byId("face-enroll-video"), id = enrollingId, session = generation;
    const images = [];
    try {
      for (let shot = 0; shot < SHOTS; shot += 1) {
        captureProgress(progress, images.length, shot + 1);
        for (let remaining = 3; remaining > 0; remaining -= 1) {
          step(`3 de 3 · Foto ${shot + 1}/${SHOTS}: ${prompts[shot]} Captura em ${remaining}…`);
          await pause(1000);
          if (session !== generation || enrollingId !== id) return;
        }
        if (session !== generation || enrollingId !== id) return;
        images.push(capture(video));
        captureProgress(progress, images.length);
      }
      step("Analisando as fotos…");
      const { ok, value } = await api(`identities/${id}/face`, "POST", { images });
      if (session !== generation || enrollingId !== id) return;
      step(ok ? value.message : (value.message || (typeof value.detail === "string" ? value.detail : "Não foi possível cadastrar o rosto.")), ok ? "success" : "error");
      if (ok) { stopCamera(video); document.dispatchEvent(new Event("everlock-identities-changed")); }
    } catch (error) {
      if (session === generation) {
        captureProgress(progress, images.length);
        step(error.name === "CameraError" ? error.message : "Não foi possível concluir o cadastro. Tente novamente.", "error");
      }
    } finally {
      images.length = 0;
      if (session === generation) { busy = false; byId("face-enroll-start").disabled = !isOn(video); }
    }
  });

  byId("face-enroll-cancel").addEventListener("click", () => { stopAll(); if (returnFocus?.isConnected) returnFocus.focus(); });

  // --- ponto de acesso facial na tela principal ------------------------------------------------
  // A decisão é sempre do servidor: esta tela só mostra o que ele respondeu e o estado da trava.
  const verifyResult = byId("face-verify-result");
  const frame = byId("camera-frame"), steps = byId("access-steps");
  const decisionBox = byId("access-decision"), decisionTitle = byId("access-decision-title");
  const timeFormat = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  let decisionShownAt = 0, recentSession = 0;

  function setStep(name) {
    const order = ["front", "turn", "analyze", "decision"];
    const current = order.indexOf(name);
    for (const item of steps.querySelectorAll("li")) {
      const index = order.indexOf(item.dataset.step);
      item.dataset.state = current < 0 ? "waiting" : index < current ? "done" : index === current ? "current" : "waiting";
      if (index === current) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current");
    }
  }

  function showDecision(outcome, title, message) {
    const last = steps.querySelector('li[data-step="decision"]');
    if (last.dataset.state === "current") last.dataset.state = outcome;
    decisionBox.dataset.outcome = outcome;
    decisionTitle.textContent = title;
    verifyResult.textContent = message;
    verifyResult.dataset.outcome = outcome === "granted" ? "success" : outcome === "denied" ? "denied" : "";
    frame.dataset.state = outcome === "granted" || outcome === "denied" ? outcome : frame.dataset.state;
    if (outcome === "granted" || outcome === "denied") decisionShownAt = Date.now();
  }

  function resetDecision(message) {
    setStep(null);
    frame.dataset.state = isOn(byId("face-verify-video")) ? "ready" : "off";
    decisionBox.dataset.outcome = "idle";
    decisionTitle.textContent = "Trava engatada";
    verifyResult.textContent = message;
    verifyResult.dataset.outcome = "";
  }

  function renderEngine() {
    const badge = byId("access-engine");
    const kind = status.engine_kind || "unknown";
    badge.dataset.kind = status.test_double ? "test" : status.available ? "real" : "off";
    badge.textContent = status.test_double ? "Motor de TESTE (não reconhece rostos reais)"
      : status.available ? "Motor local OpenCV" : kind === "opencv" ? "Motor OpenCV sem modelos" : "Motor indisponível";
  }

  // Contagem da liberação e estado da trava: vêm do estado oficial publicado por app.js.
  document.addEventListener("everlock-state", (event) => {
    const door = event.detail.door, simulation = event.detail.simulation;
    const released = door.lock === "released";
    const remaining = Math.max(0, Number(door.release_remaining_seconds) || 0);
    const meter = byId("release-meter");
    meter.hidden = !released;
    if (released) {
      const total = Number(status.release_seconds) || 3;
      byId("release-meter-bar").style.setProperty("--progress", String(Math.min(1, remaining / total)));
      byId("release-meter-label").textContent = `Trava volta a engatar em ${remaining.toFixed(1).replace(".", ",")} s virtuais${simulation.paused ? " (relógio pausado)" : ""}`;
    }
    byId("access-lock-state").textContent = released
      ? "Trava virtual LIBERADA. A porta continua fechada até alguém usar Abrir / entrar."
      : door.lock === "pending_close" ? "Porta aberta: a trava engata quando a porta for fechada."
        : "Trava virtual engatada.";
    byId("access-lock-state").dataset.lock = door.lock;
    // Depois da liberação concedida, o painel volta a mostrar a trava engatada.
    if (!released && decisionBox.dataset.outcome === "granted" && Date.now() - decisionShownAt > 1500) {
      decisionBox.dataset.outcome = "relocked";
      decisionTitle.textContent = "Trava engatada novamente";
      verifyResult.textContent = "A liberação terminou e a trava virtual voltou à posição de repouso.";
      frame.dataset.state = isOn(byId("face-verify-video")) ? "ready" : "off";
    }
  });

  async function loadRecent() {
    if (!isAdmin()) return;
    const session = sessionGeneration;
    const today = new Date();
    const day = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    try {
      const { ok, value } = await api(`events?source=recognition&since=${day}&limit=100`);
      if (!ok || session !== sessionGeneration || !isAdmin()) return;
      const items = value.items;
      const granted = items.filter((item) => item.outcome === "success").length;
      const denied = items.filter((item) => item.outcome === "denied").length;
      byId("access-today").textContent = `Hoje: ${granted} ${granted === 1 ? "liberação" : "liberações"} · ${denied} ${denied === 1 ? "recusa" : "recusas"}${value.has_more ? " (últimas 100)" : ""}`;
      const list = byId("access-recent");
      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "empty-state"; empty.textContent = "Nenhuma decisão hoje.";
        list.replaceChildren(empty);
        return;
      }
      list.replaceChildren(...items.slice(0, 6).map((item) => {
        const row = document.createElement("li");
        row.dataset.outcome = item.outcome;
        const time = document.createElement("time");
        time.dateTime = item.created_at; time.textContent = timeFormat.format(new Date(item.created_at));
        const label = document.createElement("span");
        label.className = "recent-outcome";
        label.textContent = item.outcome === "success" ? "Liberado" : item.outcome === "denied" ? "Negado" : "Info";
        const title = document.createElement("span");
        title.className = "recent-title"; title.textContent = item.title;
        row.append(time, label, title);
        return row;
      }));
    } catch { /* lista auxiliar: falhas não afetam o ponto de acesso */ }
  }

  byId("face-camera-toggle").addEventListener("click", async () => {
    const video = byId("face-verify-video"), toggle = byId("face-camera-toggle");
    if (!isAdmin() || cameraStarting) return;
    if (isOn(video)) { stopAll(); resetDecision("Câmera desligada. Nenhuma imagem foi enviada."); return; }
    stopAll();
    const session = generation;
    cameraStarting = true; toggle.disabled = true;
    frame.dataset.state = "starting";
    try {
      await startCamera(video);
      if (session !== generation) { stopCamera(video); return; }
      toggle.textContent = "Desligar câmera"; byId("face-verify").disabled = false;
      resetDecision("Câmera ligada. Centralize o rosto no guia e selecione Reconhecer e liberar.");
    } catch (error) {
      if (session === generation) {
        frame.dataset.state = "off";
        showDecision("denied", "Câmera indisponível", error.message);
      }
    } finally { cameraStarting = false; toggle.disabled = false; }
  });

  byId("face-verify").addEventListener("click", async () => {
    const video = byId("face-verify-video"), button = byId("face-verify");
    if (!isAdmin() || busy || !isOn(video)) return;
    busy = true; button.disabled = true;
    const session = generation;
    const current = () => session === generation && isAdmin() && isOn(video) && !document.hidden;
    let challengeId = null;
    try {
      frame.dataset.state = "working";
      decisionBox.dataset.outcome = "working";
      decisionTitle.textContent = "Reconhecendo…";
      setStep("front");
      verifyResult.textContent = "Preparando o desafio de movimento…";
      const challengeReply = await api("recognition/challenge", "POST", {});
      challengeId = challengeReply.value.challenge_id || null;
      if (!current()) { cancelChallenge(challengeId); return; }
      if (!challengeReply.ok) {
        setStep("decision");
        const decision = challengeReply.value.decision;
        showDecision("denied", decision?.title || "Acesso negado", challengeReply.value.message || "Não foi possível iniciar o desafio.");
        return;
      }
      activeChallenge = challengeId;
      verifyResult.textContent = "Olhe de frente para a câmera.";
      await pause(650);
      if (!current()) return;
      const front = capture(video), turned = [];
      setStep("turn");
      verifyResult.textContent = challengeReply.value.instruction;
      for (let shot = 0; shot < 6; shot += 1) {
        await pause(300);
        if (!current()) return;
        turned.push(capture(video));
      }
      setStep("analyze");
      verifyResult.textContent = "Analisando o rosto e o movimento neste computador…";
      const { ok, value } = await api("recognition/verify", "POST", {
        challenge_id: challengeId, front, turned,
      });
      if (!current()) return;
      setStep("decision");
      const decision = value.decision || { granted: ok, title: ok ? "Acesso liberado" : "Acesso negado" };
      const detail = typeof value.detail === "string" ? value.detail : "";
      if (ok && decision.granted) {
        showDecision("granted", `${decision.title} · identidade #${value.identity_id}`,
          `${value.message || "Reconhecido."} Use Abrir / entrar antes do fim do prazo.`);
      } else {
        const reason = value.message || detail || "Não foi possível reconhecer.";
        showDecision("denied", decision.title || "Acesso negado", /trava permanece engatada/i.test(reason) ? reason : `${reason} A trava permanece engatada.`);
      }
      document.dispatchEvent(new Event("everlock-identities-changed"));
    } catch (error) {
      cancelChallenge(challengeId);
      if (current()) {
        setStep("decision");
        showDecision("denied", "Acesso negado", error.name === "CameraError" ? error.message : "Falha ao falar com o servidor local. A trava permanece engatada.");
      }
    } finally {
      if (activeChallenge === challengeId) activeChallenge = null;
      if (session === generation) { busy = false; button.disabled = !isOn(video); }
      loadRecent();
    }
  });

  // Fecha a câmera ao trocar de sessão, de página ou de aba: nunca fica ligada sem uso.
  document.addEventListener("everlock-session", () => {
    sessionGeneration += 1; recentSession = sessionGeneration;
    stopAll(); resetDecision("Ligue a câmera e selecione Reconhecer. O sistema pedirá um giro curto do rosto.");
    loadStatus(); loadRecent();
  });
  window.addEventListener("hashchange", () => {
    if (isOn(byId("face-verify-video")) || activeChallenge) resetDecision("Câmera desligada ao trocar de página. Nenhuma imagem foi enviada.");
    stopAll();
    if (location.hash === "#simulador" || location.hash === "") loadRecent();
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopAll(); });
  window.addEventListener("pagehide", stopAll);
  window.setInterval(() => { if (!document.hidden && recentSession === sessionGeneration && isAdmin()) loadRecent(); }, 15000);
})();
