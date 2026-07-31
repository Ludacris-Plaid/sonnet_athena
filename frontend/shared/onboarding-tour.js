/*
  A minimal spotlight tour: highlights a real DOM element, shows a tooltip
  next to it, Next/Skip controls. Runs once per user — tracked
  server-side (has_completed_onboarding on the User model), not
  localStorage, so it doesn't reset just because someone clears browser
  storage or logs in from a different device.
*/
const TOUR_STEPS = [
  { selector: '[data-nav-key="briefing"]', title: "Start here every day", text: "Your Daily Briefing — stats, AI insights, and everything waiting on you, in one glance." },
  { selector: '[data-nav-key="inbox"]', title: "Inbox — everything in one place", text: "Client messages AND your own conversation with Athena (chat or voice) live right here, pinned at the top. She remembers everything, permanently, until you explicitly start a new conversation." },
  { selector: '[data-nav-key="search"]', title: "Search everything at once", text: "One box searches your clients, properties, documents, memories, past conversations, compliance reference, and the web." },
  { selector: '[data-nav-key="clients"]', title: "Your CRM", text: "Pipeline stages, lead scoring, and a timeline that fills itself from every email, text, and call — no manual logging." },
  { selector: '[data-nav-key="calendar"]', title: "Calendar", text: "A real calendar with two-way Google/Outlook sync." },
  { selector: '[data-nav-key="properties"]', title: "Properties", text: "Import from your choice of source, browse as cards, and get the full picture — comps, calculator, listing agent contact — in one modal." },
  { selector: '[data-nav-key="trust"]', title: "Trust with Athena", text: "Watch her earn real autonomy over time — levels, badges, and hints on how to speed it up." },
  { selector: '[data-nav-key="docs"]', title: "Docs, any time", text: "Full searchable documentation, and you can ask Athena directly about how anything works." },
];

function buildTourOverlay() {
  const overlay = document.createElement("div");
  overlay.id = "onboarding-overlay";
  overlay.innerHTML = `
    <div id="onboarding-spotlight"></div>
    <div id="onboarding-tooltip">
      <div id="onboarding-tooltip-title"></div>
      <div id="onboarding-tooltip-text"></div>
      <div id="onboarding-tooltip-footer">
        <span id="onboarding-progress"></span>
        <div>
          <button id="onboarding-skip">Skip tour</button>
          <button id="onboarding-next" class="primary">Next</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const style = document.createElement("style");
  style.textContent = `
    #onboarding-overlay { position: fixed; inset: 0; z-index: 200; pointer-events: none; }
    #onboarding-spotlight {
      position: absolute; border-radius: 12px; box-shadow: 0 0 0 9999px rgba(36,31,24,0.65);
      transition: all 0.4s cubic-bezier(0.16,1,0.3,1); pointer-events: none;
    }
    #onboarding-tooltip {
      position: absolute; background: #fff; border-radius: 14px; padding: 18px 20px; width: 280px;
      box-shadow: 0 12px 40px rgba(36,31,24,0.3); pointer-events: auto;
      transition: all 0.4s cubic-bezier(0.16,1,0.3,1); opacity: 0; transform: scale(0.95);
    }
    #onboarding-tooltip.visible { opacity: 1; transform: scale(1); }
    #onboarding-tooltip-title { font-family: var(--font-display); font-size: 16px; margin-bottom: 6px; }
    #onboarding-tooltip-text { font-size: 13px; color: var(--ink-700); line-height: 1.55; margin-bottom: 14px; }
    #onboarding-tooltip-footer { display: flex; justify-content: space-between; align-items: center; }
    #onboarding-progress { font-size: 11px; color: var(--ink-500); }
    #onboarding-skip { background: none; border: none; color: var(--ink-500); font-size: 12px; cursor: pointer; margin-right: 10px; }
    #onboarding-next { background: var(--gold-500); color: var(--ink-900); border: none; padding: 8px 16px; border-radius: 7px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
  `;
  document.head.appendChild(style);
  return overlay;
}

function positionStep(step, index, total) {
  const target = document.querySelector(step.selector);
  const spotlight = document.getElementById("onboarding-spotlight");
  const tooltip = document.getElementById("onboarding-tooltip");

  if (!target) return false; // element not on this page — caller skips to next

  const rect = target.getBoundingClientRect();
  spotlight.style.top = `${rect.top - 6}px`;
  spotlight.style.left = `${rect.left - 6}px`;
  spotlight.style.width = `${rect.width + 12}px`;
  spotlight.style.height = `${rect.height + 12}px`;

  tooltip.style.top = `${Math.min(rect.top, window.innerHeight - 220)}px`;
  tooltip.style.left = `${rect.right + 20}px`;
  tooltip.classList.add("visible");

  document.getElementById("onboarding-tooltip-title").textContent = step.title;
  document.getElementById("onboarding-tooltip-text").textContent = step.text;
  document.getElementById("onboarding-progress").textContent = `${index + 1} of ${total}`;
  document.getElementById("onboarding-next").textContent = index === total - 1 ? "Finish" : "Next";
  return true;
}

async function runOnboardingTour(onComplete) {
  const overlay = buildTourOverlay();
  let stepIndex = 0;

  function showStep() {
    while (stepIndex < TOUR_STEPS.length && !positionStep(TOUR_STEPS[stepIndex], stepIndex, TOUR_STEPS.length)) {
      stepIndex++;
    }
    if (stepIndex >= TOUR_STEPS.length) finish();
  }

  function finish() {
    overlay.remove();
    onComplete();
  }

  document.getElementById("onboarding-next").addEventListener("click", () => {
    stepIndex++;
    if (stepIndex >= TOUR_STEPS.length) finish();
    else showStep();
  });
  document.getElementById("onboarding-skip").addEventListener("click", finish);

  showStep();
}
