// PrivacyLens AI copy buttons
// 1. Per-page "Copy for AI" button (replaces edit button) — copies current page markdown
// 2. "Copy all docs" button injected into the header nav — copies llms-full.txt

const RAW_BASE = "https://raw.githubusercontent.com/Madan2248c/privacylens/main/docs/";
const SITE_BASE = "https://madan2248c.github.io/privacylens/";

async function fetchAndCopy(url, btn, successText) {
  const span = btn.querySelector("span") || btn;
  const original = span.textContent;
  try {
    const text = await fetch(url).then((r) => {
      if (!r.ok) throw new Error(r.status);
      return r.text();
    });
    await navigator.clipboard.writeText(text);
    span.textContent = "Copied!";
    setTimeout(() => (span.textContent = original), 2000);
  } catch {
    window.open(url, "_blank");
  }
}

function initPageCopyButton() {
  const btn = document.querySelector(".ai-copy-page");
  if (!btn) return;

  const srcPath = btn.getAttribute("data-src-path");
  if (!srcPath) return;

  btn.addEventListener("click", () => {
    fetchAndCopy(RAW_BASE + srcPath, btn, "Copied!");
  });
}

function initAllDocsCopyButton() {
  // Inject into the header actions area (right side of top nav)
  const headerInner = document.querySelector(".md-header__inner");
  if (!headerInner || document.getElementById("ai-copy-all-btn")) return;

  const btn = document.createElement("button");
  btn.id = "ai-copy-all-btn";
  btn.title = "Copy full docs for AI (llms-full.txt)";
  btn.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
      <path d="M19 21H8V7h11m0-2H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m-3-4H4a2 2 0 0 0-2 2v14h2V3h12V1Z"/>
    </svg>
    <span>Copy all docs for AI</span>
  `;

  Object.assign(btn.style, {
    display: "flex",
    alignItems: "center",
    gap: "0.35rem",
    padding: "0 0.8rem",
    height: "2.4rem",
    borderRadius: "1.2rem",
    border: "1px solid rgba(255,255,255,0.3)",
    background: "transparent",
    color: "var(--md-primary-bg-color)",
    fontSize: "0.75rem",
    fontWeight: "600",
    cursor: "pointer",
    whiteSpace: "nowrap",
    marginLeft: "0.5rem",
  });

  btn.addEventListener("click", () => {
    fetchAndCopy(SITE_BASE + "llms-full.txt", btn, "Copied!");
  });

  headerInner.appendChild(btn);
}

// MkDocs Material uses instant navigation — re-init on every page load
document$.subscribe(() => {
  initPageCopyButton();
  initAllDocsCopyButton();
});
