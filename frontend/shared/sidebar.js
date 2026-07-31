/*
  Renders the sidebar nav into <div id="sidebar-mount" data-active="dashboard">.
  data-active must match one of the keys in NAV_ITEMS to highlight correctly.
*/
const NAV_ITEMS = [
  { key: "athena", label: "Chat with Athena", icon: "🦉", href: "/app/dashboard.html" },
  { key: "briefing", label: "Daily Briefing", icon: "☀️", href: "/app/daily-briefing.html" },
  { key: "inbox", label: "Inbox", icon: "📥", href: "/app/inbox.html" },
  { key: "search", label: "Search", icon: "🔍", href: "/app/search.html" },
  { key: "clients", label: "Clients", icon: "👥", href: "/app/clients.html" },
  { key: "calendar", label: "Calendar", icon: "📅", href: "/app/calendar.html" },
  { key: "alerts", label: "Alerts", icon: "🔔", href: "/app/alerts.html", badge: true },
  { key: "properties", label: "Properties", icon: "🏠", href: "/app/properties.html" },
  { key: "dealroom", label: "Deal Room", icon: "📋", href: "/app/deal-room.html" },
  { key: "content", label: "Content Studio", icon: "✍️", href: "/app/content-studio.html" },
  { key: "documents", label: "Documents", icon: "📄", href: "/app/documents.html" },
  { key: "opportunities", label: "Opportunities", icon: "🎯", href: "/app/opportunities.html" },
  { key: "investment", label: "Investment Calculator", icon: "📈", href: "/app/investment-calculator.html" },
  { key: "compliance", label: "Compliance", icon: "⚖️", href: "/app/compliance.html" },
  { key: "memories", label: "Memories", icon: "🧠", href: "/app/memories.html" },
  { key: "trust", label: "Trust with Athena", icon: "🤝", href: "/app/trust.html" },
  { key: "docs", label: "Docs", icon: "📚", href: "/app/docs.html" },
  { key: "settings", label: "Settings", icon: "⚙️", href: "/app/settings.html" },
];

async function renderSidebar() {
  const mount = document.getElementById("sidebar-mount");
  if (!mount) return;
  const active = mount.dataset.active;

  const links = NAV_ITEMS.map(
    (item) => `
    <a class="sidebar-link ${item.key === active ? "active" : ""}" href="${item.href}" data-nav-key="${item.key}">
      <span class="ic">${item.icon}</span> ${item.label}
      ${item.badge ? `<span class="nav-badge" id="nav-badge-${item.key}" style="display:none;"></span>` : ""}
    </a>`
  ).join("");

  mount.innerHTML = `
    <div class="sidebar-brand">🦉 Athena</div>
    <div class="sidebar-nav">${links}</div>
    <div class="sidebar-footer" id="logout-trigger">
      <div class="avatar-chip">U</div>
      <div>Log out</div>
    </div>
  `;

  document.getElementById("logout-trigger").addEventListener("click", async () => {
    await auth.clearToken();
    window.location.href = "/app/login.html";
  });

  // Mobile: inject a hamburger toggle into the topbar (if this page has
  // one) and a tap-to-close backdrop, so the fixed sidebar becomes a real
  // slide-in drawer on small screens instead of just squishing the layout.
  const topbar = document.querySelector(".topbar");
  if (topbar && !document.querySelector(".mobile-menu-btn")) {
    const menuBtn = document.createElement("button");
    menuBtn.className = "mobile-menu-btn";
    menuBtn.setAttribute("aria-label", "Open menu");
    menuBtn.textContent = "☰";
    topbar.prepend(menuBtn);

    const backdrop = document.createElement("div");
    backdrop.className = "mobile-sidebar-backdrop";
    document.body.appendChild(backdrop);

    const openDrawer = () => { mount.classList.add("mobile-open"); backdrop.classList.add("visible"); };
    const closeDrawer = () => { mount.classList.remove("mobile-open"); backdrop.classList.remove("visible"); };

    menuBtn.addEventListener("click", openDrawer);
    backdrop.addEventListener("click", closeDrawer);
    mount.querySelectorAll(".sidebar-link").forEach((link) => link.addEventListener("click", closeDrawer));
  }

  // Populate the Alerts unread badge, if the user is actually logged in
  // (this runs on every page, so fail quietly if not authenticated yet).
  try {
    if (await auth.isLoggedIn()) {
      const { unread_count } = await api.unreadAlertCount();
      const badgeEl = document.getElementById("nav-badge-alerts");
      if (badgeEl && unread_count > 0) {
        badgeEl.textContent = unread_count > 9 ? "9+" : unread_count;
        badgeEl.style.display = "inline-flex";
      }
    }
  } catch (e) {
    // Not fatal — badge just doesn't show if the alerts endpoint isn't reachable yet.
  }

  // Populate the real user name/avatar in the topbar, wherever the page
  // has one — replaces the "Test Agent" placeholder that used to be
  // hardcoded on every single page individually. One fetch, one place to
  // fix, shows up everywhere the topbar exists.
  try {
    const topbarName = document.querySelector(".topbar-user .name");
    if (topbarName && (await auth.isLoggedIn())) {
      const profile = await api.getProfile();
      const displayName = profile.full_name || profile.email || "Agent";
      topbarName.textContent = displayName;

      const avatarEl = document.querySelector(".topbar-user .avatar-chip");
      if (avatarEl) avatarEl.textContent = displayName[0].toUpperCase();
    }
  } catch (e) {
    // Not fatal — topbar just keeps whatever static text the page shipped with.
  }
}

document.addEventListener("DOMContentLoaded", renderSidebar);
