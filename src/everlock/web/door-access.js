"use strict";

// "Meu acesso pela porta": a própria pessoa registra o aceite, cadastra o rosto da porta, apaga o
// cadastro ou revoga o consentimento. Horário, retenção e ativação são do administrador. As fotos
// viram JPEG só na memória e vão ao servidor local; nada é salvo no navegador.
(() => {
  const byId = (id) => document.getElementById(id);
  const kit = window.FaceKit;
  const SHOTS = 5;
  const prompts = [
    "Olhe de frente para a câmera.", "Continue de frente, relaxado.",
    "Vire o rosto bem pouco para a esquerda.", "Vire o rosto bem pouco para a direita.",
    "Volte a olhar de frente. Última foto!",
  ];
  const states = {
    ready: "Pronta: o rosto pode liberar a trava dentro do horário.",
    not_enrolled: "Sem cadastro facial ainda.",
    inactive: "Desativada pelo administrador.",
    revoked: "Consentimento revogado.",
  };
  const dayNames = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
  const video = byId("door-access-video"), progress = byId("door-access-progress");
  let view = null, generation = 0, busy = false, cameraStarting = false;

  const step = (text, outcome = "info") => {
    byId("door-access-step").textContent = text;
    byId("door-access-step").dataset.outcome = outcome;
  };
  const dateText = (seconds) => new Date(seconds * 1000).toLocaleDateString("pt-BR");
  const scheduleText = (schedule) => `${schedule.days.length === 7 ? "todos os dias" : schedule.days.map((day) => dayNames[day]).join(", ")}, das ${schedule.start} às ${schedule.end}`;

  function stopCamera() {
    generation += 1;
    kit.stop(video);
    busy = false; cameraStarting = false;
    kit.captureProgress(progress);
    byId("door-access-start").disabled = true;
    byId("door-access-password").value = "";
  }

  function fact(term, detail) {
    const wrap = document.createElement("div");
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = term; dd.textContent = detail;
    wrap.append(dt, dd);
    return wrap;
  }

  function render(showFlow = false) {
    const status = byId("door-access-status"), facts = byId("door-access-facts");
    const flow = byId("door-access-flow"), manage = byId("door-access-manage");
    if (!view) { status.textContent = "Não foi possível consultar seu acesso agora."; facts.hidden = flow.hidden = manage.hidden = true; return; }
    if (!view.linked) {
      status.textContent = "Sua conta ainda não está vinculada a uma identidade da porta. Peça a um administrador para criar a identidade com o vínculo à sua conta; depois, você mesmo registra o aceite e o rosto aqui.";
      facts.hidden = flow.hidden = manage.hidden = true;
      return;
    }
    const identity = view.identity, consent = identity.consent;
    const revoked = consent.revoked_at !== null;
    status.textContent = revoked
      ? "Você revogou o consentimento. Os vetores foram apagados e o rosto não libera mais a trava. Para voltar, peça uma nova identidade ao administrador."
      : identity.face_samples
        ? "Seu rosto está cadastrado para a porta. O servidor confere horário, retenção e ativação a cada tentativa."
        : "Leia o termo, registre o seu aceite e cadastre o rosto com a câmera deste computador.";
    facts.replaceChildren(
      fact("Identidade", `#${identity.id} · ${identity.label}`),
      fact("Situação", states[identity.state] || identity.state),
      fact("Agora", identity.access_now.message),
      fact("Horário permitido", scheduleText(identity.schedule)),
      fact("Exclusão automática", dateText(identity.expires_at)),
      fact("Seu aceite", consent.subject_confirmed_at ? `${dateText(consent.subject_confirmed_at)} · ${consent.subject_method === "own_account" ? "registrado por você" : "declarado com o administrador"}` : "ainda não registrado"),
      fact("Cadastro facial", identity.face_samples ? `${identity.face_samples} amostras (vetores cifrados; nenhuma imagem)` : "nenhum"),
    );
    facts.hidden = false;
    const engineOk = view.engine.available;
    flow.hidden = revoked || !(showFlow || !identity.face_samples);
    manage.hidden = revoked;
    byId("door-access-redo").hidden = !identity.face_samples;
    byId("door-access-remove").hidden = !identity.face_samples;
    byId("door-access-term").textContent = `Termo ${view.policy.version}: ${view.policy.text}`;
    if (!flow.hidden && !engineOk) step(`${view.engine.reason} O cadastro pela câmera fica indisponível até o motor voltar.`, "error");
    byId("door-access-prepare").disabled = !engineOk || !byId("door-access-consent").checked || cameraStarting || kit.isOn(video);
  }

  async function load(showFlow = false) {
    const session = generation;
    try {
      const { ok, value } = await kit.request("me/door-access");
      if (session !== generation) return;
      view = ok ? value : null;
    } catch { if (session === generation) view = null; }
    render(showFlow);
  }

  byId("door-access-consent").addEventListener("change", () => {
    if (!byId("door-access-consent").checked && (cameraStarting || kit.isOn(video))) { stopCamera(); step("Câmera desligada. Sem o aceite, nada é capturado."); }
    byId("door-access-prepare").disabled = !byId("door-access-consent").checked || !view?.engine?.available || cameraStarting || kit.isOn(video);
  });

  byId("door-access-prepare").addEventListener("click", async () => {
    if (busy || cameraStarting || kit.isOn(video) || !byId("door-access-consent").checked || !view?.linked) return;
    const session = generation;
    cameraStarting = true;
    byId("door-access-prepare").disabled = true;
    try {
      const consent = await kit.request("me/door-access/consent", "POST", { accepted: true, version: view.policy.version });
      if (session !== generation) return;
      if (!consent.ok) throw new Error(kit.messageOf(consent.value, "Não foi possível registrar o aceite."));
      await kit.start(video);
      if (session !== generation) { kit.stop(video); return; }
      kit.captureProgress(progress, 0);
      step("Aceite registrado. Câmera ligada: boa iluminação, só você no enquadramento. Digite sua senha e inicie quando estiver pronto.");
      byId("door-access-start").disabled = false;
      byId("door-access-password").focus();
    } catch (error) {
      if (session === generation) step(error.message, "error");
    } finally {
      cameraStarting = false;
      if (session === generation) byId("door-access-prepare").disabled = !byId("door-access-consent").checked || kit.isOn(video);
    }
  });

  byId("door-access-start").addEventListener("click", async () => {
    if (busy || !kit.isOn(video)) return;
    const password = byId("door-access-password").value;
    if (!password) { step("Digite sua senha atual para confirmar o cadastro.", "error"); byId("door-access-password").focus(); return; }
    busy = true; byId("door-access-start").disabled = true;
    const session = generation, images = [];
    try {
      for (let shot = 0; shot < SHOTS; shot += 1) {
        kit.captureProgress(progress, images.length, shot + 1);
        for (let remaining = 3; remaining > 0; remaining -= 1) {
          step(`Foto ${shot + 1}/${SHOTS}: ${prompts[shot]} Captura em ${remaining}…`);
          await kit.pause(1000);
          if (session !== generation) return;
        }
        images.push(kit.capture(video));
        kit.captureProgress(progress, images.length);
      }
      step("Analisando as fotos neste computador…");
      const { ok, value } = await kit.request("me/door-access/face", "POST", { password, images });
      if (session !== generation) return;
      if (ok) {
        step(value.message, "success");
        kit.stop(video);
        byId("door-access-consent").checked = false;
        view = value.access; render(false);
      } else {
        step(kit.messageOf(value, "Não foi possível cadastrar o rosto."), "error");
      }
    } catch (error) {
      if (session === generation) {
        kit.captureProgress(progress, images.length);
        step(error.name === "CameraError" ? error.message : "Não foi possível concluir o cadastro. Tente novamente.", "error");
      }
    } finally {
      images.length = 0;
      byId("door-access-password").value = "";
      if (session === generation) { busy = false; byId("door-access-start").disabled = !kit.isOn(video); }
    }
  });

  byId("door-access-cancel").addEventListener("click", () => { stopCamera(); step("Câmera desligada. Nenhuma foto foi enviada."); });
  byId("door-access-redo").addEventListener("click", () => { stopCamera(); render(true); byId("door-access-consent").focus(); });

  async function manageAction(path, method, question) {
    if (busy || !window.confirm(question)) return;
    stopCamera();
    busy = true;
    try {
      const { ok, value } = await kit.request(path, method);
      step(kit.messageOf(value, ok ? "Concluído." : "Não foi possível concluir."), ok ? "success" : "error");
      if (ok && value.access) { view = value.access; }
    } catch { step("Falha ao falar com o servidor local.", "error"); }
    finally { busy = false; render(false); }
  }
  byId("door-access-remove").addEventListener("click", () => manageAction("me/door-access/face", "DELETE",
    "Apagar seu cadastro facial da porta? Os vetores cifrados são excluídos e o rosto deixa de liberar a trava."));
  byId("door-access-revoke").addEventListener("click", () => manageAction("me/door-access/revoke", "POST",
    "Revogar o consentimento apaga o cadastro facial e impede novos cadastros nesta identidade. Continuar?"));

  // Câmera nunca fica ligada fora desta tela, em outra aba ou depois de sair.
  document.addEventListener("everlock-session", () => { stopCamera(); view = null; step(""); if (document.body.dataset.role) load(); });
  window.addEventListener("hashchange", () => { stopCamera(); if (location.hash === "#contas" && document.body.dataset.role) load(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopCamera(); });
  window.addEventListener("pagehide", () => kit.stop(video));
})();
