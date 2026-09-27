"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  let setup = false;
  let registering = false;
  let user = null;
  const passwordRule = "Use pelo menos 6 caracteres, com maiúscula, minúscula, número e caractere especial (. ? @ $, por exemplo). Sem limite máximo.";
  const validPassword = (value) => Array.from(value).length >= 6 && /\p{Lu}/u.test(value) && /\p{Ll}/u.test(value) && /\p{Nd}/u.test(value) && /[\p{P}\p{S}]/u.test(value);
  const message = (text) => { byId("account-message").textContent = text; };

  function checkPassword(input, required = true) {
    input.setCustomValidity(required && !validPassword(input.value) ? passwordRule : "");
  }

  function renderAuth() {
    const creating = setup || registering;
    byId("auth-title").textContent = setup ? "Prepare seu EverLock" : registering ? "Crie sua conta" : "Entre no EverLock";
    byId("auth-description").textContent = setup ? "Crie o primeiro administrador deste computador. Não há senha padrão." : registering ? "Faça seu cadastro. Um administrador precisa aprová-lo antes do primeiro acesso." : "Use sua conta local para acessar o laboratório.";
    byId("auth-submit").textContent = setup ? "Criar administrador" : registering ? "Solicitar cadastro" : "Entrar";
    byId("login-password").autocomplete = creating ? "new-password" : "current-password";
    byId("password-rules").hidden = !creating;
    byId("confirm-password-label").hidden = !creating;
    byId("confirm-password").disabled = !creating;
    byId("confirm-password").required = creating;
    byId("auth-mode").hidden = setup;
    byId("auth-mode").textContent = registering ? "Já tenho conta. Entrar" : "Não tem conta? Criar conta";
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
      const detail = Array.isArray(value.detail) ? value.detail.map((item) => item.msg.replace(/^Value error, /, "")).join(" ") : value.detail;
      throw new Error(typeof detail === "string" ? detail : "Confira os campos informados.");
    }
    return value;
  }

  function showSession(value) {
    setup = value.setup_required;
    user = value.user;
    if (user?.role !== "admin") {
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
    if (user || setup) registering = false;
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
      label.textContent = `${item.username} · ${item.role === "admin" ? "Administrador" : "Usuário"} · ${item.pending ? "Aguardando aprovação" : item.active ? "Ativo" : "Desativado"}`;
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
      row.append(label, role, apply, toggle); fragment.append(row);
    }
    byId("account-list").replaceChildren(fragment);
    const history = await api("events");
    byId("account-history").replaceChildren(...history.items.map((item) => {
      const row = document.createElement("li"); row.textContent = `${new Date(item.created_at).toLocaleString("pt-BR")} · ${item.actor || "Sistema"}: ${item.detail}`; return row;
    }));
  }

  byId("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    checkPassword(byId("login-password"), setup || registering);
    const confirmation = byId("confirm-password");
    confirmation.setCustomValidity((setup || registering) && confirmation.value !== byId("login-password").value ? "A confirmação da senha não confere." : "");
    if (!event.target.reportValidity()) return;
    const button = byId("auth-submit"); button.disabled = true;
    const data = Object.fromEntries(new FormData(event.target));
    try {
      if (registering && !setup) {
        const result = await api("register", "POST", data);
        event.target.reset(); registering = false; renderAuth(); byId("auth-message").textContent = result.message;
        return;
      }
      delete data.confirm_password;
      if (setup) await api("setup", "POST", data);
      await api("login", "POST", data);
      event.target.reset(); byId("auth-message").textContent = ""; await refresh();
    } catch (error) { byId("auth-message").textContent = error.message; }
    finally { button.disabled = false; }
  });
  byId("auth-mode").addEventListener("click", () => {
    registering = !registering; byId("login-form").reset(); byId("auth-message").textContent = ""; renderAuth();
  });
  byId("login-password").addEventListener("input", () => {
    checkPassword(byId("login-password"), setup || registering); byId("confirm-password").setCustomValidity("");
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
  refresh();
})();
