"use strict";

(() => {
  const main = document.getElementById("main");
  const breadcrumb = document.getElementById("breadcrumb-page");
  const pages = Array.from(main.querySelectorAll(":scope > section[id]"));
  const pageIds = new Set(pages.map((page) => page.id));
  let sessionReady = false;
  let displayedPage = null;
  const toggle = document.getElementById("nav-toggle");
  function closeMenu() { document.body.classList.remove("menu-open"); toggle.setAttribute("aria-expanded", "false"); }
  toggle.addEventListener("click", () => {
    const open = document.body.classList.toggle("menu-open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && document.body.classList.contains("menu-open")) { closeMenu(); toggle.focus(); } });

  function pageFromHash() {
    const id = location.hash.slice(1);
    return pageIds.has(id) ? id : "simulador";
  }

  function renderPage() {
    const id = pageFromHash();
    if (!id) return;
    let activePage = pages.find((page) => page.id === id);
    if (sessionReady && activePage.hasAttribute("data-admin")
        && document.body.dataset.role !== "admin") {
      activePage = pages.find((page) => page.id === "simulador");
      history.replaceState(null, "", `${location.pathname}${location.search}#simulador`);
    }

    const visible = sessionReady && !main.hidden;
    for (const page of pages) {
      page.hidden = page !== activePage;
      if (!visible || page !== activePage) page.classList.remove("page-enter");
    }
    if (visible && activePage !== displayedPage) activePage.classList.add("page-enter");
    displayedPage = visible ? activePage : null;
    const activeLink = document.querySelector(`.nav-link[href="#${activePage.id}"]`);
    for (const link of document.querySelectorAll(".nav-link")) {
      const isActive = link === activeLink;
      link.classList.toggle("active", isActive);
      if (isActive) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }

    const label = activeLink?.textContent.trim() || "Simulador";
    breadcrumb.textContent = label;
    document.title = `EverLock · ${label}`;
    window.scrollTo({ top: 0, behavior: "instant" });
    closeMenu();
    if (sessionReady && !main.hidden) {
      const heading = activePage.querySelector("h1, h2");
      heading?.setAttribute("tabindex", "-1"); heading?.focus({ preventScroll: true });
    }
  }

  window.addEventListener("hashchange", renderPage);
  document.addEventListener("everlock-session", () => {
    sessionReady = true;
    renderPage();
  });
  renderPage();
})();
