"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  let setup = false;
  let registering = false;
  let unconfirmed = false;
  let resetToken = null;
  let user = null;
  const passwordRule = "Use pelo menos 6 caracteres, com maiúscula, minúscula, número e caractere especial (. ? @ $, por exemplo). Sem limite máximo.";
  const validPassword = (value) => Array.from(value).length >= 6 && /\p{Lu}/u.test(value) && /\p{Ll}/u.test(value) && /\p{Nd}/u.test(value) && /[\p{P}\p{S}]/u.test(value);
  const message = (text) => { byId("account-message").textContent = text; };

  function checkPassword(input, required = true) {
    input.setCustomValidity(required && !validPassword(input.value) ? passwordRule : "");
  }

  // Modo "nova senha": aberto pelo link do e-mail (#redefinir=...). Só pede a senha e a confirmação.
  function renderReset() {
    byId("auth-title").textContent = "Crie uma nova senha";
    byId("auth-description").textContent = "Escolha uma senha nova para a sua conta. Depois de salvar, entre com ela.";
    byId("auth-submit").textContent = "Salvar nova senha";
    for (const [label, input] of [["identifier-label", "identifier"], ["username-label", "reg-username"], ["email-label", "reg-email"], ["role-label", "reg-role"], ["invite-label", "reg-invite"]]) {
      byId(label).hidden = true;
      byId(input).disabled = true;
      byId(input).required = false;
    }
    byId("role-hint").hidden = true;
    byId("login-password").autocomplete = "new-password";
    byId("password-rules").hidden = false;
    byId("confirm-password-label").hidden = false;
    byId("confirm-password").disabled = false;
    byId("confirm-password").required = true;
    byId("auth-mode").hidden = false;
    byId("auth-mode").textContent = "Voltar ao login";
    byId("resend-confirmation").hidden = true;
    byId("forgot-password").hidden = true;
    document.dispatchEvent(new CustomEvent("everlock-auth-mode", { detail: { registering: true } }));
    byId("login-password").setCustomValidity("");
    byId("confirm-password").setCustomValidity("");
  }

  function renderAuth() {
    if (resetToken) { renderReset(); return; }
    const creating = registering;
    byId("auth-title").textContent = creating ? "Crie sua conta" : "Entre no EverLock";
    byId("auth-description").textContent = creating
      ? setup
        ? "Cadastre a primeira conta, que será a de administrador deste EverLock."
        : "Informe um e-mail válido. Enviaremos uma mensagem para você confirmar a conta antes do primeiro acesso."
      : setup
        ? "Este EverLock ainda não tem contas. Use “Cadastrar-se” para criar a conta de administrador."
        : "Entre com seu e-mail ou usuário e a senha. Se ainda não tem conta, faça o cadastro.";
    byId("auth-submit").textContent = creating ? "Cadastrar" : "Entrar";
    for (const [label, input, visible] of [
      ["identifier-label", "identifier", !creating],
      ["username-label", "reg-username", creating],
      ["email-label", "reg-email", creating],
    ]) {
      byId(label).hidden = !visible;
      byId(input).disabled = !visible;
      byId(input).required = visible;
    }
    // Na primeira conta o papel é sempre administrador; depois, quem se cadastra escolhe.
    const choosing = creating && !setup;
    const wantsAdmin = choosing && byId("reg-role").value === "admin";
    for (const [label, input, visible] of [
      ["role-label", "reg-role", choosing],
      ["invite-label", "reg-invite", wantsAdmin],
    ]) {
      byId(label).hidden = !visible;
      byId(input).disabled = !visible;
      byId(input).required = visible && input === "reg-invite";
    }
    byId("role-hint").hidden = !choosing;
    byId("role-hint").textContent = wantsAdmin
      ? "Administrador: controla cenários de teste, contas, identidades e histórico. Use o código gerado por outro administrador."
      : "Usuário: acompanha a porta, envia comandos pelo painel remoto e troca a própria senha.";
    byId("login-password").autocomplete = creating ? "new-password" : "current-password";
    byId("password-rules").hidden = !creating;
    byId("confirm-password-label").hidden = !creating;
    byId("confirm-password").disabled = !creating;
    byId("confirm-password").required = creating;
    byId("auth-mode").hidden = false;
    byId("auth-mode").textContent = creating ? "Já tenho conta. Entrar" : "Não tem conta? Cadastrar-se";
    byId("resend-confirmation").hidden = creating || !unconfirmed;
    byId("forgot-password").hidden = creating;
    document.dispatchEvent(new CustomEvent("everlock-auth-mode", { detail: { registering: creating } }));
    byId("login-password").setCustomValidity("");
    byId("confirm-password").setCustomValidity("");
  }

  async function api(path, method = "GET", body) {
    const response = await fetch(`/api/auth/${path}`, {
      method, credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(10000),
    });
    const value = await response.json();
    if (!response.ok) {
      if (response.status === 401 && path !== "login") await refresh();
      const detail = Array.isArray(value.detail) ? value.detail.map((item) => item.msg.replace(/^Value error, /, "")).join(" ") : value.detail?.message ?? value.detail;
      const failure = new Error(typeof detail === "string" ? detail : "Confira os campos informados.");
      failure.code = value.detail?.code;
      throw failure;
    }
    return value;
  }

  function showSession(value) {
    setup = value.setup_required;
    user = value.user;
    byId("invite-new").hidden = true; byId("invite-code").textContent = "";
    if (user?.role !== "admin") {
      byId("invite-list").replaceChildren();
      byId("account-list").replaceChildren();
      byId("account-history").replaceChildren();
      byId("new-user-form").reset();
    }
    byId("password-form").reset();
    if (!user) message("");
    document.body.dataset.role = user?.role || "";
    byId("auth-panel").hidden = Boolean(user);
    byId("main").hidden = !user;
    byId("logout").hidden = !user;
    byId("session-label").textContent = user ? `${user.username} · ${user.role === "admin" ? "Administrador" : "Usuário"}` : "";
    if (user) registering = false;
    renderAuth();
    document.dispatchEvent(new Event("everlock-session"));
  }

  async function refresh() {
    try {
      const value = await api("session");
      showSession(value);
      if (user?.role === "admin") await loadUsers();
    } catch {
      byId("auth-message").textContent = "Não foi possível consultar a sessão. Verifique se o servidor está aberto.";
    }
  }

  async function loadUsers() {
    const { items } = await api("users");
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const row = document.createElement("div"); row.className = "account-row";
      const label = document.createElement("span");
      const status = item.pending ? "Aguardando aprovação" : !item.email_confirmed ? "E-mail não confirmado" : item.active ? "Ativo" : "Desativado";
      label.textContent = `${item.username}${item.email ? ` (${item.email})` : ""} · ${item.role === "admin" ? "Administrador" : "Usuário"} · ${status}`;
      const role = document.createElement("select");
      role.setAttribute("aria-label", `Papel de ${item.username}`);
      for (const [value, text] of [["user", "Usuário"], ["admin", "Administrador"]]) {
        const option = document.createElement("option"); option.value = value; option.textContent = text; role.append(option);
      }
      role.value = item.role;
      const apply = document.createElement("button"); apply.className = "button button-secondary"; apply.textContent = "Salvar papel";
      const toggle = document.createElement("button"); toggle.className = "button button-secondary"; toggle.textContent = item.pending ? "Aprovar cadastro" : item.active ? "Desativar" : "Reativar";
      if (item.pending) { role.disabled = true; apply.textContent = "Recusar cadastro"; }
      const change = async (nextRole, active) => {
        apply.disabled = toggle.disabled = true;
        try { const result = await api(`users/${item.id}`, "PATCH", { role: nextRole, active }); message(result.message); await refresh(); }
        catch (error) { message(error.message); apply.disabled = toggle.disabled = false; }
      };
      apply.addEventListener("click", () => change(item.pending ? "user" : role.value, Boolean(item.active)));
      toggle.addEventListener("click", () => change(item.role, !item.active));
      row.append(label, role, apply, toggle);
      if (item.face_samples) {
        const drop = document.createElement("button"); drop.className = "button button-secondary"; drop.textContent = "Remover rosto";
        drop.addEventListener("click", async () => {
          drop.disabled = true;
          try { message((await api(`users/${item.id}/face`, "DELETE")).message); await refresh(); }
          catch (error) { message(error.message); drop.disabled = false; }
        });
        row.append(drop);
      }
      fragment.append(row);
    }
    byId("account-list").replaceChildren(fragment);
    await loadInvites();
    const history = await api("events");
    byId("account-history").replaceChildren(...history.items.map((item) => {
      const row = document.createElement("li"); row.textContent = `${new Date(item.created_at).toLocaleString("pt-BR")} · ${item.actor || "Sistema"}: ${item.detail}`; return row;
    }));
  }

  async function loadInvites() {
    const { items } = await api("invites");
    byId("invite-list").replaceChildren(...items.map((item) => {
      const row = document.createElement("div"); row.className = "invite-row";
      const label = document.createElement("span");
      label.textContent = `Convite #${item.id} · criado por ${item.created_by} · vale até ${new Date(item.expires_at * 1000).toLocaleString("pt-BR")}`;
      const revoke = document.createElement("button"); revoke.className = "button button-quiet"; revoke.textContent = "Revogar";
      revoke.addEventListener("click", async () => {
        revoke.disabled = true;
        try { message((await api(`invites/${item.id}`, "DELETE")).message); await loadInvites(); }
        catch (error) { message(error.message); revoke.disabled = false; }
      });
      row.append(label, revoke); return row;
    }));
  }

  byId("create-invite").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      const invite = await api("invites", "POST", {});
      byId("invite-code").textContent = invite.code; byId("invite-new").hidden = false;
      message("Convite criado. Copie o código agora: ele não será mostrado de novo.");
      await loadInvites();
    } catch (error) { message(error.message); }
    finally { event.target.disabled = false; }
  });
  byId("copy-invite").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(byId("invite-code").textContent); message("Código copiado."); }
    catch { message("Não foi possível copiar. Selecione o código e copie manualmente."); }
  });

  const authText = (text) => { byId("auth-message").textContent = text; };

  byId("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const choosing = registering || resetToken !== null;
    checkPassword(byId("login-password"), choosing);
    const confirmation = byId("confirm-password");
    confirmation.setCustomValidity(choosing && confirmation.value !== byId("login-password").value ? "A confirmação da senha não confere." : "");
    if (!event.target.reportValidity()) return;
    const button = byId("auth-submit"); button.disabled = true;
    const password = byId("login-password").value;
    unconfirmed = false;
    try {
      if (resetToken) {
        const result = await api("reset-password", "POST", { token: resetToken, password, confirm_password: confirmation.value });
        event.target.reset(); resetToken = null; registering = false; renderAuth(); authText(result.message);
        return;
      }
      if (!registering) {
        if (setup) { authText("Ainda não há uma conta neste EverLock. Use “Cadastrar-se” para criar a conta de administrador."); return; }
        await api("login", "POST", { identifier: byId("identifier").value, password });
      } else {
        const username = byId("reg-username").value, email = byId("reg-email").value;
        if (setup) {
          await api("setup", "POST", { username, email, password });
          await api("login", "POST", { identifier: username, password });
        } else {
          const body = { username, email, password, confirm_password: confirmation.value, role: byId("reg-role").value };
          if (body.role === "admin") body.invite_code = byId("reg-invite").value;
          const result = await api("register", "POST", body);
          event.target.reset(); registering = false; renderAuth(); authText(result.message);
          return;
        }
      }
      event.target.reset(); authText(""); await refresh();
    } catch (error) {
      unconfirmed = error.code === "email_unconfirmed";
      authText(error.message); renderAuth();
    } finally { button.disabled = false; }
  });
  byId("forgot-password").addEventListener("click", async () => {
    const identifier = byId("identifier").value.trim();
    if (identifier.length < 3) {
      authText("Digite seu e-mail ou usuário no campo acima e clique de novo em “Esqueci minha senha”.");
      byId("identifier").focus();
      return;
    }
    const button = byId("forgot-password"); button.disabled = true;
    try { authText((await api("forgot-password", "POST", { identifier })).message); }
    catch (error) { authText(error.message); }
    finally { button.disabled = false; }
  });
  byId("resend-confirmation").addEventListener("click", async () => {
    const button = byId("resend-confirmation"); button.disabled = true;
    try {
      const result = await api("resend-confirmation", "POST", { identifier: byId("identifier").value, password: byId("login-password").value });
      authText(result.message);
    } catch (error) { authText(error.message); }
    finally { button.disabled = false; }
  });
  byId("reg-role").addEventListener("change", renderAuth);
  byId("auth-mode").addEventListener("click", () => {
    if (resetToken) { resetToken = null; registering = false; } else registering = !registering;
    unconfirmed = false; byId("login-form").reset(); byId("auth-message").textContent = ""; renderAuth();
  });
  byId("login-password").addEventListener("input", () => {
    checkPassword(byId("login-password"), registering); byId("confirm-password").setCustomValidity("");
  });
  byId("confirm-password").addEventListener("input", () => byId("confirm-password").setCustomValidity(""));
  document.querySelectorAll("[data-new-password]").forEach((input) => {
    input.addEventListener("input", () => checkPassword(input));
  });
  byId("logout").addEventListener("click", async () => {
    try { await api("logout", "POST", {}); showSession({ setup_required: false, user: null }); }
    catch { message("Não foi possível confirmar a saída. Tente novamente."); }
  });
  byId("auth-refresh").addEventListener("click", refresh);
  byId("new-user-form").addEventListener("submit", async (event) => {
    event.preventDefault(); checkPassword(event.target.elements.password);
    if (!event.target.reportValidity()) return;
    const button = event.target.querySelector("button"); button.disabled = true;
    try { const result = await api("users", "POST", Object.fromEntries(new FormData(event.target))); event.target.reset(); message(result.message); await loadUsers(); }
    catch (error) { message(error.message); }
    finally { button.disabled = false; }
  });
  byId("password-form").addEventListener("submit", async (event) => {
    event.preventDefault(); checkPassword(event.target.elements.new_password);
    if (!event.target.reportValidity()) return;
    const button = event.target.querySelector("button"); button.disabled = true;
    try { const result = await api("password", "POST", Object.fromEntries(new FormData(event.target))); event.target.reset(); await refresh(); byId("auth-message").textContent = result.message; }
    catch (error) { message(error.message); }
    finally { button.disabled = false; }
  });
  document.addEventListener("everlock-login-required", () => {
    if (user) { showSession({setup_required: false, user: null}); byId("auth-message").textContent = "Sua sessão expirou ou foi revogada. Entre novamente."; }
  });
  // O link do e-mail traz o token no fragmento (#confirmar=...), que nunca chega ao servidor.
  async function confirmFromLink() {
    const reset = /^#redefinir=([A-Za-z0-9_-]{20,128})$/.exec(location.hash);
    if (reset) {
      history.replaceState(null, "", location.pathname + location.search);
      resetToken = reset[1]; registering = false; renderAuth();
      authText("Link aceito. Escolha a nova senha.");
      return;
    }
    const match = /^#confirmar=([A-Za-z0-9_-]{20,128})$/.exec(location.hash);
    if (!match) return;
    history.replaceState(null, "", location.pathname + location.search);
    try {
      const result = await api("confirm-email", "POST", { token: match[1] });
      authText(result.message); message(result.message);
    } catch (error) { authText(error.message); message(error.message); }
  }
  document.addEventListener("everlock-face-login", () => refresh());
  refresh().then(confirmFromLink);
})();
