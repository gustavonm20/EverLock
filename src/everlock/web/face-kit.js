"use strict";

// Peças comuns da câmera e das chamadas ao servidor, usadas pelo reconhecimento da porta
// (faces.js) e pelo rosto da conta (face-login.js). As fotos viram JPEG só em memória.
(() => {
  const streams = new Map(); // elemento <video> -> MediaStream
  const pause = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  function cameraError(error) {
    if (error.name === "NotAllowedError") return "A câmera foi bloqueada. Libere o acesso nas permissões do navegador (ícone ao lado do endereço).";
    if (error.name === "NotFoundError") return "Nenhuma câmera foi encontrada neste computador.";
    if (error.name === "NotReadableError") return "A câmera está em uso por outro programa. Feche-o e tente de novo.";
    return `Não foi possível abrir a câmera (${error.name || "erro"}).`;
  }

  function stop(video) {
    streams.get(video)?.getTracks().forEach((track) => track.stop());
    streams.delete(video);
    video.srcObject = null;
    video.hidden = true;
  }

  async function start(video) {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Este navegador não permite usar a câmera nesta página.");
    stop(video);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false });
      streams.set(video, stream);
      video.srcObject = stream;
      video.hidden = false;
      await video.play();
    } catch (error) {
      stop(video);
      throw new Error(cameraError(error));
    }
  }

  function capture(video) {
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 640 / (video.videoWidth || 640));
    canvas.width = Math.round((video.videoWidth || 640) * scale);
    canvas.height = Math.round((video.videoHeight || 480) * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
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

  window.FaceKit = Object.freeze({ start, stop, capture, request, messageOf, pause, isOn: (video) => streams.has(video) });
})();
