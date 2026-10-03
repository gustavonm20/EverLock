"use strict";

// Câmera do navegador para o reconhecimento facial. As fotos viram JPEG em memória, são enviadas
// ao servidor local e nunca são salvas: nem aqui, nem lá. Só admins usam estes recursos.
(() => {
  const byId = (id) => document.getElementById(id);
  const SHOTS = 5, SHOT_INTERVAL_MS = 900;
  const prompts = [
    "Olhe de frente para a câmera.", "Continue de frente, relaxado.",
    "Vire o rosto bem pouco para a esquerda.", "Vire o rosto bem pouco para a direita.",
    "Volte a olhar de frente. Última foto!",
  ];
  const { start: startCamera, stop: stopCamera, capture, pause, isOn, request: api } = window.FaceKit;
  let status = { available: false, reason: "Verificando…" };
  let enrollingId = null, busy = false, generation = 0, sessionGeneration = 0;
  let cameraStarting = false, activeChallenge = null;

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

  document.addEventListener("everlock-face-enroll", async (event) => {
    if (!isAdmin() || busy || cameraStarting) return;
    stopAll();
    const session = generation;
    const panel = byId("face-enroll-panel");
    panel.hidden = false; enrollingId = event.detail.id;
    byId("face-enroll-title").textContent = `Cadastro facial da identidade #${enrollingId}`;
    byId("face-enroll-start").disabled = !status.available;
    panel.scrollIntoView({ block: "nearest" });
    if (!status.available) { step(`${status.reason}`, "error"); return; }
    cameraStarting = true; byId("face-enroll-start").disabled = true;
    try {
      await startCamera(byId("face-enroll-video"));
      if (session !== generation) { stopCamera(byId("face-enroll-video")); return; }
      step("Câmera ligada. Posicione o rosto no centro e clique em Iniciar captura.");
      byId("face-enroll-start").disabled = false;
    } catch (error) {
      if (session === generation) { step(error.message, "error"); byId("face-enroll-start").disabled = true; }
    } finally { cameraStarting = false; }
  });

  byId("face-enroll-start").addEventListener("click", async () => {
    if (!isAdmin() || busy || enrollingId === null || !isOn(byId("face-enroll-video"))) return;
    busy = true; byId("face-enroll-start").disabled = true;
    const video = byId("face-enroll-video"), id = enrollingId, session = generation;
    try {
      const images = [];
      for (let shot = 0; shot < SHOTS; shot += 1) {
        step(`Foto ${shot + 1} de ${SHOTS}: ${prompts[shot]}`);
        await pause(SHOT_INTERVAL_MS);
        if (session !== generation || enrollingId !== id) return;
        images.push(capture(video));
      }
      step("Analisando as fotos…");
      const { ok, value } = await api(`identities/${id}/face`, "POST", { images });
      if (session !== generation || enrollingId !== id) return;
      step(ok ? value.message : (value.message || (typeof value.detail === "string" ? value.detail : "Não foi possível cadastrar o rosto.")), ok ? "success" : "error");
      if (ok) { stopCamera(video); document.dispatchEvent(new Event("everlock-identities-changed")); }
    } catch {
      if (session === generation) step("Não foi possível concluir o cadastro. Tente novamente.", "error");
    } finally {
      if (session === generation) { busy = false; byId("face-enroll-start").disabled = !isOn(video); }
    }
  });

  byId("face-enroll-cancel").addEventListener("click", stopAll);

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
    } catch {
      cancelChallenge(challengeId);
      if (current()) { verifyResult.textContent = "Falha ao falar com o servidor local."; verifyResult.dataset.outcome = "denied"; }
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
