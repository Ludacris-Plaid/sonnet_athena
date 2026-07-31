/*
  Renders the admin top nav into <div id="admin-nav-mount" data-active="dashboard">.
  Distinct dark styling from the regular app sidebar — this is a
  deliberately different visual register ("control room") so it's always
  obvious you're in the platform-admin area, not the customer-facing app.
*/
const ADMIN_NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", href: "/admin/dashboard.html" },
  { key: "users", label: "Users", href: "/admin/users.html" },
  { key: "audit", label: "Audit Log", href: "/admin/audit-log.html" },
  { key: "athena", label: "Ask Athena", href: "/admin/athena.html" },
  { key: "settings", label: "Platform Settings", href: "/admin/settings.html" },
];

async function renderAdminNav() {
  const mount = document.getElementById("admin-nav-mount");
  if (!mount) return;
  const active = mount.dataset.active;

  mount.innerHTML = `
    <div class="admin-nav-inner">
      <div class="admin-brand">🦉 Athena — Platform Admin</div>
      <div class="admin-nav-links">
        ${ADMIN_NAV_ITEMS.map(
          (item) => `<a class="admin-nav-link ${item.key === active ? "active" : ""}" href="${item.href}">${item.label}</a>`
        ).join("")}
      </div>
      <div class="admin-nav-right">
        <span id="admin-email-display" style="font-size:12.5px; opacity:0.7;"></span>
        <button id="admin-logout-btn" class="admin-logout-btn">Log out</button>
      </div>
    </div>
  `;

  document.getElementById("admin-logout-btn").addEventListener("click", async () => {
    await auth.clearToken();
    window.location.href = "/admin/login.html";
  });

  // Verify admin status server-side, not just presence of a session —
  // a non-admin who happens to be logged in to the regular app should
  // never see admin content even briefly.
  try {
    const me = await api.adminMe();
    document.getElementById("admin-email-display").textContent = me.email;
  } catch (e) {
    await auth.clearToken();
    window.location.href = "/admin/login.html";
  }
}

document.addEventListener("DOMContentLoaded", renderAdminNav);
