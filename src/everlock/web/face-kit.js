"use strict";

// Peças comuns da câmera e das chamadas ao servidor, usadas pelo reconhecimento da porta
// (faces.js) e pelo rosto da conta (face-login.js). As fotos viram JPEG só em memória.
(() => {
  const streams = new Map(); // elemento <video> -> MediaStream
  const starts = new Map(); // elemento <video> -> abertura cancelável
  const pause = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
  const cameraFailure = (message) => Object.assign(new Error(message), { name: "CameraError" });
  const cancelled = () => cameraFailure("Solicitação de câmera cancelada.");

  function waitFor(promise, signal, milliseconds, message) {
    return new Promise((resolve, reject) => {
      const finish = (callback, value) => {
        window.clearTimeout(timer);
        signal.removeEventListener("abort", onAbort);
        callback(value);
      };
      const onAbort = () => finish(reject, cancelled());
      const timer = window.setTimeout(() => finish(reject, cameraFailure(message)), milliseconds);
      signal.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted) onAbort();
      Promise.resolve(promise).then((value) => finish(resolve, value), (error) => finish(reject, error));
    });
  }

  function firstFrame(video, signal) {
    return new Promise((resolve, reject) => {
      const events = ["loadeddata", "canplay", "resize"];
      const clean = () => {
        events.forEach((event) => video.removeEventListener(event, ready));
        signal.removeEventListener("abort", onAbort);
      };
      const ready = () => {
        if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
          clean(); resolve();
        }
      };
      const onAbort = () => { clean(); reject(cancelled()); };
      events.forEach((event) => video.addEventListener(event, ready));
      signal.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted) onAbort(); else ready();
    });
  }

  function cameraError(error) {
    if (error.name === "CameraError") return error.message;
    if (error.name === "NotAllowedError") return "A câmera foi bloqueada. Libere o acesso nas permissões do navegador (ícone ao lado do endereço).";
    if (error.name === "NotFoundError") return "Nenhuma câmera foi encontrada neste computador.";
    if (error.name === "NotReadableError") return "A câmera está em uso por outro programa. Feche-o e tente de novo.";
    return `Não foi possível abrir a câmera (${error.name || "erro"}).`;
  }

  function stop(video) {
    starts.get(video)?.abort();
    starts.delete(video);
    streams.get(video)?.getTracks().forEach((track) => track.stop());
    streams.delete(video);
    video.srcObject = null;
    video.hidden = true;
  }

  async function start(video) {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Este navegador não permite usar a câmera nesta página.");
    stop(video);
    const controller = new AbortController();
    starts.set(video, controller);
    let stream;
    try {
      const pending = navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false });
      // A permissão do navegador não pode ser abortada; encerre qualquer retorno tardio.
      pending.then((late) => {
        if (controller.signal.aborted) late.getTracks().forEach((track) => track.stop());
      }, () => {});
      stream = await waitFor(pending, controller.signal, 15000, "A câmera não respondeu. Confira a permissão do navegador e tente novamente.");
      if (controller.signal.aborted) throw cancelled();
      streams.set(video, stream);
      video.srcObject = stream;
      video.hidden = false;
      const playing = Promise.resolve().then(() => video.play());
      await waitFor(Promise.all([firstFrame(video, controller.signal), playing]), controller.signal, 10000, "A câmera abriu, mas não enviou imagem. Confira o dispositivo e tente novamente.");
    } catch (error) {
      controller.abort();
      stream?.getTracks().forEach((track) => track.stop());
      if (starts.get(video) === controller) stop(video);
      throw cameraFailure(cameraError(error));
    } finally {
      if (starts.get(video) === controller) starts.delete(video);
    }
  }

  function capture(video) {
    if (!streams.has(video) || !streams.get(video).getVideoTracks().some((track) => track.readyState === "live") || video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      throw cameraFailure("A câmera ainda não tem uma imagem disponível. Confira a prévia e tente novamente.");
    }
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 640 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
  }

  function captureProgress(element, completed = null, current = null) {
    element.hidden = completed === null;
    const shots = [...element.querySelectorAll("li")];
    element.querySelector("[data-capture-count]").textContent = `${completed ?? 0} de ${shots.length}`;
    shots.forEach((shot, index) => {
      const done = index < (completed ?? 0), active = index + 1 === current;
      shot.dataset.state = done ? "done" : active ? "current" : "waiting";
      shot.textContent = done ? "✓" : String(index + 1);
      shot.setAttribute("aria-label", `Foto ${index + 1}: ${done ? "capturada" : active ? "em preparação" : "aguardando"}`);
      if (active) shot.setAttribute("aria-current", "step");
      else shot.removeAttribute("aria-current");
    });
  }

  async function request(path, method = "GET", body) {
    const response = await fetch(`/api/${path}`, {
      method, credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(25000),
    });
    const value = await response.json();
    return { status: response.status, ok: response.ok, value };
  }

  // Texto de erro de qualquer resposta: mensagem própria, detalhe simples ou erros de validação.
  function messageOf(value, fallback) {
    if (value?.message) return value.message;
    if (typeof value?.detail === "string") return value.detail;
    if (Array.isArray(value?.detail)) return value.detail.map((item) => String(item.msg).replace(/^Value error, /, "")).join(" ");
    return fallback;
  }

  window.FaceKit = Object.freeze({ start, stop, capture, captureProgress, request, messageOf, pause, isOn: (video) => streams.has(video) });
})();
