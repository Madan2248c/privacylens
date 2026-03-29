const RAW_BASE = "https://raw.githubusercontent.com/Madan2248c/privacylens/main/docs/";
const SITE_BASE = "https://madan2248c.github.io/privacylens/";

async function fetchAndCopy(url, onSuccess) {
  try {
    const text = await fetch(url).then((r) => r.text());
    await navigator.clipboard.writeText(text);
    onSuccess();
  } catch {
    window.open(url, "_blank");
  }
}

document$.subscribe(() => {
  // --- Per-page copy button (where edit button was) ---
  const pageBtn = document.querySelector(".ai-copy-page");
  if (pageBtn) {
    const srcPath = pageBtn.getAttribute("data-src-path");
    pageBtn.addEventListener("click", () => {
      fetchAndCopy(RAW_BASE + srcPath, () => {
        pageBtn.classList.add("ai-copied");
        setTimeout(() => pageBtn.classList.remove("ai-copied"), 2000);
      });
    });
  }

  // --- Floating "copy all docs" icon button ---
  if (document.getElementById("ai-copy-all")) return;

  const btn = document.createElement("button");
  btn.id = "ai-copy-all";
  btn.title = "Copy full docs for AI";
  btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M19 21H8V7h11m0-2H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m-3-4H4a2 2 0 0 0-2 2v14h2V3h12V1Z"/></svg>`;

  document.body.appendChild(btn);

  btn.addEventListener("click", () => {
    fetchAndCopy(SITE_BASE + "llms-full.txt", () => {
      btn.classList.add("ai-copied");
      setTimeout(() => btn.classList.remove("ai-copied"), 2000);
    });
  });
});
