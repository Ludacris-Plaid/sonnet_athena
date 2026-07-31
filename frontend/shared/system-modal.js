/*
  Drop-in replacements for the browser's native alert()/confirm(), styled
  with the platform's own design system instead of the browser chrome.
  Both are async (return a Promise) — since every call site in this app is
  already inside an async event handler, `await systemAlert(...)` /
  `await systemConfirm(...)` swaps in cleanly wherever `alert(...)` /
  `confirm(...)` used to be.
*/
function _ensureSystemModalStyles() {
  if (document.getElementById("system-modal-styles")) return;
  const style = document.createElement("style");
  style.id = "system-modal-styles";
  style.textContent = `
    .system-modal-backdrop {
      position: fixed; inset: 0; background: rgba(36,31,24,0.55); z-index: 500;
      display: flex; align-items: center; justify-content: center; opacity: 0;
      transition: opacity 0.2s; padding: 20px;
    }
    .system-modal-backdrop.visible { opacity: 1; }
    .system-modal-box {
      background: #fff; border-radius: 16px; padding: 26px; width: 380px; max-width: 100%;
      box-shadow: 0 20px 60px rgba(36,31,24,0.35); transform: scale(0.94); transition: transform 0.2s;
    }
    .system-modal-backdrop.visible .system-modal-box { transform: scale(1); }
    .system-modal-icon { font-size: 26px; margin-bottom: 10px; }
    .system-modal-message { font-size: 14px; color: var(--ink-900, #241f18); line-height: 1.55; margin-bottom: 20px; white-space: pre-wrap; }
    .system-modal-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .system-modal-btn {
      padding: 9px 18px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; border: none;
    }
    .system-modal-btn.primary { background: var(--gold-500, #c99a3e); color: var(--ink-900, #241f18); }
    .system-modal-btn.outline { background: transparent; border: 1px solid var(--olive-200, #d8d2bf); color: var(--ink-700, #4a4436); }

    /* On mobile, this becomes a bottom sheet that slides up — matching
       the same motion language as every other mobile surface in the app,
       rather than a centered dialog that feels like a desktop leftover. */
    @media (max-width: 640px) {
      .system-modal-backdrop { align-items: flex-end; padding: 0; }
      .system-modal-box {
        width: 100%; border-radius: 18px 18px 0 0; padding: 22px 20px calc(22px + env(safe-area-inset-bottom));
        transform: translateY(100%);
      }
      .system-modal-backdrop.visible .system-modal-box { transform: translateY(0); }
    }
  `;
  document.head.appendChild(style);
}

function _buildBackdrop() {
  _ensureSystemModalStyles();
  const backdrop = document.createElement("div");
  backdrop.className = "system-modal-backdrop";
  document.body.appendChild(backdrop);
  requestAnimationFrame(() => backdrop.classList.add("visible"));
  return backdrop;
}

function systemAlert(message, icon = "ℹ️") {
  return new Promise((resolve) => {
    const backdrop = _buildBackdrop();
    backdrop.innerHTML = `
      <div class="system-modal-box">
        <div class="system-modal-icon">${icon}</div>
        <div class="system-modal-message">${message}</div>
        <div class="system-modal-actions">
          <button class="system-modal-btn primary" id="system-modal-ok">OK</button>
        </div>
      </div>`;
    document.getElementById("system-modal-ok").addEventListener("click", () => {
      backdrop.remove();
      resolve();
    });
  });
}

function systemConfirm(message, { confirmLabel = "Confirm", danger = false, icon = "⚠️" } = {}) {
  return new Promise((resolve) => {
    const backdrop = _buildBackdrop();
    backdrop.innerHTML = `
      <div class="system-modal-box">
        <div class="system-modal-icon">${icon}</div>
        <div class="system-modal-message">${message}</div>
        <div class="system-modal-actions">
          <button class="system-modal-btn outline" id="system-modal-cancel">Cancel</button>
          <button class="system-modal-btn primary" id="system-modal-confirm" style="${danger ? "background:var(--danger,#a8432f); color:#fff;" : ""}">${confirmLabel}</button>
        </div>
      </div>`;
    document.getElementById("system-modal-cancel").addEventListener("click", () => {
      backdrop.remove();
      resolve(false);
    });
    document.getElementById("system-modal-confirm").addEventListener("click", () => {
      backdrop.remove();
      resolve(true);
    });
  });
}
