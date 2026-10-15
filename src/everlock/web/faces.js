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
    if (status.available) {
      title.textContent = "Reconhecimento facial por câmera";
      text.textContent = `Motor: ${status.model}. A câmera pede um giro curto do rosto antes de reconhecer. As imagens são descartadas logo após a análise. Reconhecer só libera a trava virtual; para entrar, use “Abrir / entrar”.`;
    } else {
      title.textContent = "Reconhecimento por câmera indisponível";
      text.textContent = `${status.reason} O teste simulado abaixo continua funcionando. Abrir este painel não liga a câmera nem libera a porta.`;
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

  // --- reconhecimento na tela principal -----------------------------------------------------
  const verifyResult = byId("face-verify-result");
  byId("face-camera-toggle").addEventListener("click", async () => {
    const video = byId("face-verify-video"), toggle = byId("face-camera-toggle");
    if (!isAdmin() || cameraStarting) return;
    if (isOn(video)) { stopAll(); return; }
    stopAll();
    const session = generation;
    cameraStarting = true; toggle.disabled = true;
    try {
      await startCamera(video);
      if (session !== generation) { stopCamera(video); return; }
      toggle.textContent = "Desligar câmera"; byId("face-verify").disabled = false;
      verifyResult.textContent = "Câmera ligada. Fique de frente e clique em Reconhecer."; verifyResult.dataset.outcome = "";
    } catch (error) {
      if (session === generation) { verifyResult.textContent = error.message; verifyResult.dataset.outcome = "denied"; }
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
      verifyResult.textContent = "Preparando o desafio de movimento…";
      const challengeReply = await api("recognition/challenge", "POST", {});
      challengeId = challengeReply.value.challenge_id || null;
      if (!current()) { cancelChallenge(challengeId); return; }
      if (!challengeReply.ok) {
        verifyResult.textContent = challengeReply.value.message || "Não foi possível iniciar o desafio.";
        verifyResult.dataset.outcome = "denied";
        return;
      }
      activeChallenge = challengeId;
      verifyResult.textContent = "Olhe de frente para a câmera.";
      await pause(650);
      if (!current()) return;
      const front = capture(video), turned = [];
      verifyResult.textContent = challengeReply.value.instruction;
      for (let frame = 0; frame < 6; frame += 1) {
        await pause(300);
        if (!current()) return;
        turned.push(capture(video));
      }
      verifyResult.textContent = "Analisando o rosto e o movimento…";
      const { ok, value } = await api("recognition/verify", "POST", {
        challenge_id: challengeId, front, turned,
      });
      if (!current()) return;
      const detail = typeof value.detail === "string" ? value.detail : "";
      verifyResult.textContent = ok ? `${value.message || "Reconhecido."}` : (value.message || detail || "Não foi possível reconhecer.");
      verifyResult.dataset.outcome = ok ? "success" : "denied";
      document.dispatchEvent(new Event("everlock-identities-changed"));
    } catch (error) {
      cancelChallenge(challengeId);
      if (current()) { verifyResult.textContent = error.name === "CameraError" ? error.message : "Falha ao falar com o servidor local."; verifyResult.dataset.outcome = "denied"; }
    } finally {
      if (activeChallenge === challengeId) activeChallenge = null;
      if (session === generation) { busy = false; button.disabled = !isOn(video); }
    }
  });

  // Fecha a câmera ao trocar de sessão, de página ou de aba: nunca fica ligada sem uso.
  document.addEventListener("everlock-session", () => { sessionGeneration += 1; stopAll(); loadStatus(); });
  window.addEventListener("hashchange", stopAll);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopAll(); });
  window.addEventListener("pagehide", stopAll);
})();
