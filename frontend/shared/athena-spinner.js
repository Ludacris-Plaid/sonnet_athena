/*
  Athena's spinner: the owl (reusing the same favicon SVG, so the brand
  mark is consistent everywhere) sits still in the center while two arcs
  spin in opposite directions around it — one gold, one olive, so the
  motion itself reads as "two things working at once," not just a
  generic loading ring. Three sizes (sm/md/lg), and an optional rotating
  message line for the big, front-and-center moments (Athena's own chat)
  — small spinners elsewhere in the app stay quiet, since a caption on
  every little inline spinner would be more noise than signal.

  Usage:
    const spinner = createAthenaSpinner(containerEl, { size: "lg", messages: true });
    spinner.start();
    ...
    spinner.stop();
*/
const ATHENA_LOADING_MESSAGES = [
  "Reading through everything relevant…",
  "Checking that against your real data, not guessing…",
  "Athena's actually thinking, not just pretending to…",
  "Cross-referencing the details that matter…",
  "One more pass to make sure this is actually right…",
  "Weighing a couple of ways to say this…",
  "Making sure nothing here contradicts what you told her earlier…",
  "Tip: you can tell Athena to keep replies short in Settings > Profile.",
  "Tip: the Search tab looks across everything at once — clients, docs, the web.",
  "Tip: every draft she writes gets fair-housing screened automatically.",
  "Fun fact: owls can rotate their heads about 270°. Athena's just thinking, though.",
  "Somewhere, a lead is about to get a much faster reply than the industry average.",
  "Grounding this in your actual clients and listings, not a generic answer…",
  "Almost there — good answers take a beat longer than fast ones…",
  "Tip: the more drafts you send unedited, the more she earns your trust.",
  "Double-checking the numbers before saying anything about them…",
  "Tip: ask her to 'go deep' for anything that needs real research.",
  "Thinking like a colleague would, not a search engine…",
  "Built with real estate agents, for real estate agents — indicationsmedia.com",
  "Powered by a partnership with indicationsmedia.com…",
  "Making sure this sounds like you, not a form letter…",
  "Give her a second — she'd rather be right than fast…",
  "Checking your memory bank for anything relevant she already knows…",
  "Owls are famously good listeners. So is she.",
  "Lining up the facts before the opinion…",
];

function _athenaSpinnerStyles() {
  if (document.getElementById("athena-spinner-styles")) return;
  const style = document.createElement("style");
  style.id = "athena-spinner-styles";
  style.textContent = `
    .athena-spinner-wrap { display: inline-flex; flex-direction: column; align-items: center; gap: 12px; }
    .athena-spinner-ring-box { position: relative; }
    .athena-spinner-ring-box .owl-center {
      position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
      border-radius: 50%; background: var(--cream, #faf6ef); padding: 4px;
    }
    .athena-spinner-arc {
      position: absolute; top: 0; left: 0; border-radius: 50%; border: 3px solid transparent;
    }
    .athena-spinner-arc.a1 { border-top-color: var(--gold-500, #c99a3e); border-right-color: var(--gold-500, #c99a3e); animation: athena-spin-cw 1.1s linear infinite; }
    .athena-spinner-arc.a2 { border-bottom-color: var(--olive-700, #536242); border-left-color: var(--olive-700, #536242); animation: athena-spin-ccw 1.5s linear infinite; }
    @keyframes athena-spin-cw { to { transform: rotate(360deg); } }
    @keyframes athena-spin-ccw { to { transform: rotate(-360deg); } }

    .athena-spinner-msg {
      font-size: 12.5px; color: var(--ink-500, #837b6b); text-align: center; max-width: 320px;
      min-height: 18px; transition: opacity 0.3s;
    }
    .athena-spinner-msg.fading { opacity: 0; }

    /* sizes */
    .athena-spinner-ring-box.sm { width: 22px; height: 22px; }
    .athena-spinner-ring-box.sm .athena-spinner-arc { width: 22px; height: 22px; border-width: 2px; }
    .athena-spinner-ring-box.sm .owl-center { width: 12px; height: 12px; }
    .athena-spinner-ring-box.sm .owl-center img { width: 12px; height: 12px; }

    .athena-spinner-ring-box.md { width: 40px; height: 40px; }
    .athena-spinner-ring-box.md .athena-spinner-arc { width: 40px; height: 40px; border-width: 3px; }
    .athena-spinner-ring-box.md .owl-center { width: 22px; height: 22px; }
    .athena-spinner-ring-box.md .owl-center img { width: 22px; height: 22px; }

    .athena-spinner-ring-box.lg { width: 84px; height: 84px; }
    .athena-spinner-ring-box.lg .athena-spinner-arc { width: 84px; height: 84px; border-width: 5px; }
    .athena-spinner-ring-box.lg .owl-center { width: 46px; height: 46px; }
    .athena-spinner-ring-box.lg .owl-center img { width: 46px; height: 46px; }
  `;
  document.head.appendChild(style);
}

function createAthenaSpinner(container, { size = "md", messages = false } = {}) {
  _athenaSpinnerStyles();

  let messageInterval = null;
  const wrap = document.createElement("div");
  wrap.className = "athena-spinner-wrap";
  wrap.innerHTML = `
    <div class="athena-spinner-ring-box ${size}">
      <div class="athena-spinner-arc a1"></div>
      <div class="athena-spinner-arc a2"></div>
      <div class="owl-center"><img src="../shared/assets/favicon.svg" alt="" /></div>
    </div>
    ${messages ? '<div class="athena-spinner-msg" id="athena-spinner-msg-text"></div>' : ""}
  `;

  function start() {
    container.innerHTML = "";
    container.appendChild(wrap);
    if (messages) {
      const msgEl = wrap.querySelector("#athena-spinner-msg-text");
      let idx = Math.floor(Math.random() * ATHENA_LOADING_MESSAGES.length);
      msgEl.textContent = ATHENA_LOADING_MESSAGES[idx];
      messageInterval = setInterval(() => {
        msgEl.classList.add("fading");
        setTimeout(() => {
          idx = (idx + 1) % ATHENA_LOADING_MESSAGES.length;
          msgEl.textContent = ATHENA_LOADING_MESSAGES[idx];
          msgEl.classList.remove("fading");
        }, 300);
      }, 2200);
    }
  }

  function stop() {
    if (messageInterval) clearInterval(messageInterval);
    if (wrap.parentElement === container) container.innerHTML = "";
  }

  return { start, stop };
}
