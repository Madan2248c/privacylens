// Inject a "Copy docs for AI" button into every page.
// Clicking it fetches llms-full.txt and copies it to the clipboard.

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.createElement("button");
  btn.id = "ai-copy-btn";
  btn.title = "Copy full docs to clipboard for use with AI assistants";
  btn.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
    </svg>
    <span>Copy docs for AI</span>
  `;

  Object.assign(btn.style, {
    position: "fixed",
    bottom: "1.5rem",
    right: "1.5rem",
    zIndex: "999",
    display: "flex",
    alignItems: "center",
    gap: "0.4rem",
    padding: "0.5rem 0.9rem",
    borderRadius: "2rem",
    border: "none",
    background: "var(--md-primary-fg-color)",
    color: "var(--md-primary-bg-color)",
    fontSize: "0.8rem",
    fontWeight: "600",
    cursor: "pointer",
    boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
    transition: "opacity 0.2s",
  });

  btn.addEventListener("mouseenter", () => (btn.style.opacity = "0.85"));
  btn.addEventListener("mouseleave", () => (btn.style.opacity = "1"));

  btn.addEventListener("click", async () => {
    const base = document.querySelector('meta[name="site-url"]')?.getAttribute("content")
      ?? window.location.origin + window.location.pathname.replace(/\/[^/]*$/, "/");
    const url = new URL("llms-full.txt", base).href;

    try {
      const text = await fetch(url).then((r) => r.text());
      await navigator.clipboard.writeText(text);
      const span = btn.querySelector("span");
      if (span) {
        span.textContent = "Copied!";
        setTimeout(() => (span.textContent = "Copy docs for AI"), 2000);
      }
    } catch {
      window.open(url, "_blank");
    }
  });

  document.body.appendChild(btn);
});
