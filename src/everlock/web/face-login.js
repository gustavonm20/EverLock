"use strict";

// Entrar com o rosto (tela de login) e cadastrar o rosto da própria conta (página Conta).
// Nada de imagem é guardado: as fotos vão ao servidor local só para análise.
(() => {
  const byId = (id) => document.getElementById(id);
  const { start, stop, capture, pause, request, messageOf } = window.FaceKit;
  const SHOTS = 5, SHOT_INTERVAL_MS = 900, TURN_FRAMES = 6, TURN_INTERVAL_MS = 450;
  const prompts = [
    "Olhe de frente para a câmera.", "Continue de frente, relaxado.",
    "Vire o rosto bem pouco para a esquerda.", "Vire o rosto bem pouco para a direita.",
    "Volte a olhar de frente. Última foto!",
  ];
  const titles = {
    no_match: "Face não cadastrada",
    no_faces_enrolled: "Nenhuma face cadastrada",
    liveness_failed: "Movimento não detectado",
    face_changed: "Rosto não confere",
    ambiguous: "Rosto ambíguo",
    rate_limited: "Aguarde um pouco",
    challenge_expired: "Tempo esgotado",
  };
  let busy = false, registering = false, generation = 0, sessionGeneration = 0;
  let cameraStarting = false, activeChallenge = null, accountAvailable = false;

  // --- entrar com o rosto ---------------------------------------------------------------------
  const box = byId("face-login-box"), panel = byId("face-login-panel"), video = byId("face-login-video");

  const showLogin = (title, message, outcome = "info") => {
    byId("face-login-title").textContent = title;
    byId("face-login-title").dataset.outcome = outcome;
    byId("face-login-message").textContent = message;
  };

  function updateBox() { box.hidden = registering || box.dataset.available !== "true"; }

  async function loadAvailability() {
    try {
      const { ok, value } = await request("auth/face/availability");
      box.dataset.available = ok && value.available ? "true" : "false";
    } catch { box.dataset.available = "false"; }
    updateBox();
  }

  function cancelChallenge(id) {
    if (!id) return;
    fetch(`/api/auth/face/challenge/${encodeURIComponent(id)}`, {
      method: "DELETE", credentials: "same-origin", keepalive: true,
      headers: { "Content-Type": "application/json" },
    }).catch(() => {});
  }

  function stopAll() {
    generation += 1;
    cancelChallenge(activeChallenge); activeChallenge = null;
    stop(video); stop(accountVideo);
    panel.hidden = true; byId("face-login").hidden = false; busy = false;
    byId("account-face-submit").disabled = !accountAvailable;
  }

  const closeLogin = () => stopAll();

  async function runFaceLogin() {
    if (busy || cameraStarting || registering || document.body.dataset.role) return;
    stopAll();
    busy = true;
    const operation = generation;
    const current = () => operation === generation && !document.hidden && !document.body.dataset.role && !registering;
    let challengeId = null;
    byId("face-login").hidden = true; panel.hidden = false;
    showLogin("Abrindo a câmera…", "Permita o acesso à câmera se o navegador pedir.");
    try {
      cameraStarting = true;
      try { await start(video); } finally { cameraStarting = false; }
      if (!current()) { stop(video); return; }
      showLogin("Olhe de frente", "Fique parado, de frente para a câmera.");
      await pause(1600);
      if (!current()) return;
      const front = capture(video);
      const challenge = await request("auth/face/challenge", "POST", {});
      challengeId = challenge.value.challenge_id || null;
      if (!current()) { cancelChallenge(challengeId); return; }
      if (!challenge.ok) throw new Error(messageOf(challenge.value, "Não foi possível iniciar o desafio."));
      activeChallenge = challengeId;
      showLogin("Agora, o movimento", challenge.value.instruction);
      await pause(700);
      if (!current()) return;
      const turned = [];
      for (let frame = 0; frame < TURN_FRAMES; frame += 1) {
        if (!current()) return;
        turned.push(capture(video)); await pause(TURN_INTERVAL_MS);
      }
      if (!current()) return;
      stop(video);
      showLogin("Verificando…", "Comparando com os rostos cadastrados.");
      const result = await request("auth/face/login", "POST", { challenge_id: challengeId, front, turned });
      if (!current()) return;
      if (result.ok) {
        panel.hidden = true; byId("face-login").hidden = false; busy = false;
        document.dispatchEvent(new Event("everlock-face-login"));
        return;
      }
      showLogin(titles[result.value.code] || "Não foi possível entrar", messageOf(result.value, "Tente de novo ou entre com e-mail e senha."), "denied");
    } catch (error) {
      cancelChallenge(challengeId);
      if (current()) showLogin("Não foi possível entrar", error.message || "Tente de novo ou entre com e-mail e senha.", "denied");
    } finally {
      if (activeChallenge === challengeId) activeChallenge = null;
      if (operation === generation) { stop(video); byId("face-login").hidden = false; busy = false; }
    }
    if (current()) byId("face-login").textContent = "Tentar de novo com o rosto";
  }

  byId("face-login").addEventListener("click", runFaceLogin);
  byId("face-login-cancel").addEventListener("click", closeLogin);
  document.addEventListener("everlock-auth-mode", (event) => { registering = event.detail.registering; if (registering) stopAll(); updateBox(); });

  // --- rosto da própria conta (página Conta) --------------------------------------------------
  const form = byId("account-face-form"), accountVideo = byId("account-face-video");
  const step = (text, outcome = "info") => { byId("account-face-step").textContent = text; byId("account-face-step").dataset.outcome = outcome; };

  async function loadAccountFace() {
    if (document.body.dataset.role === undefined || document.body.dataset.role === "") return;
    const session = sessionGeneration;
    try {
      const { ok, value } = await request("auth/face/me");
      if (!ok || session !== sessionGeneration || !document.body.dataset.role) return;
      accountAvailable = value.available;
      const when = value.enrolled_at ? new Date(value.enrolled_at * 1000).toLocaleDateString("pt-BR") : "";
      byId("account-face-status").textContent = !value.available
        ? `Indisponível neste computador: ${value.reason}`
        : value.enrolled
          ? `Rosto cadastrado em ${when} (${value.samples} amostras). Você pode entrar pela tela de login com “Entrar com o rosto”.`
          : "Nenhum rosto cadastrado. Cadastre para entrar sem digitar a senha. A senha continua funcionando sempre.";
      byId("account-face-consent").textContent = value.consent.text;
      byId("account-face-remove").hidden = !value.enrolled;
      byId("account-face-submit").textContent = value.enrolled ? "Refazer meu rosto" : "Cadastrar meu rosto";
      for (const control of form.querySelectorAll("input, #account-face-submit")) control.disabled = !value.available;
    } catch { /* a página mostra o último estado conhecido */ }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || cameraStarting || !document.body.dataset.role || !form.reportValidity()) return;
    stopAll();
    busy = true; byId("account-face-submit").disabled = true;
    const operation = generation;
    const current = () => operation === generation && !document.hidden && Boolean(document.body.dataset.role);
    const password = form.elements.password.value, consent = form.elements.consent.checked;
    try {
      cameraStarting = true;
      try { await start(accountVideo); } finally { cameraStarting = false; }
      if (!current()) { stop(accountVideo); return; }
      step("Câmera ligada. Olhe para ela.");
      const images = [];
      for (let shot = 0; shot < SHOTS; shot += 1) {
        step(`Foto ${shot + 1} de ${SHOTS}: ${prompts[shot]}`);
        await pause(SHOT_INTERVAL_MS);
        if (!current()) return;
        images.push(capture(accountVideo));
      }
      stop(accountVideo);
      step("Analisando as fotos…");
      const { ok, value } = await request("auth/face/enroll", "POST", {
        password, consent, images,
      });
      if (!current()) return;
      step(ok ? value.message : messageOf(value, "Não foi possível cadastrar o rosto."), ok ? "success" : "error");
      if (ok) form.reset();
    } catch (error) { if (current()) step(error.message, "error"); }
    finally {
      if (operation === generation) { stop(accountVideo); busy = false; byId("account-face-submit").disabled = false; }
    }
    if (current()) await loadAccountFace();
  });

  byId("account-face-remove").addEventListener("click", async () => {
    if (busy || !window.confirm("Remover seu rosto? Você continuará entrando com e-mail ou usuário e senha.")) return;
    const operation = generation;
    busy = true;
    try {
      const { ok, value } = await request("auth/face", "DELETE");
      if (operation !== generation) return;
      step(messageOf(value, "Rosto removido."), ok ? "success" : "error");
    } catch { if (operation === generation) step("Não foi possível remover agora.", "error"); }
    finally { if (operation === generation) busy = false; }
    if (operation === generation) await loadAccountFace();
  });

  // A câmera nunca fica ligada sem uso: fecha ao trocar de sessão, de página ou de aba.
  document.addEventListener("everlock-session", () => { sessionGeneration += 1; stopAll(); form.reset(); step(""); loadAccountFace(); });
  window.addEventListener("hashchange", stopAll);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopAll(); });
  window.addEventListener("pagehide", stopAll);
  loadAvailability();
})();
