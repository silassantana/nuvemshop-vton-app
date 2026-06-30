// Widget is served from the same Railway origin as the backend,
// so relative URLs work — no hardcoded domain needed.
const BACKEND_URL = "";

// ── State ───────────────────────────────────────────────────────────────────
let garmentUrl = null;
let category = "tops";
let personFile = null;
let isExpanded = false;

// ── Resize reporting (NubeSDK autoresize protocol) ─────────────────────────
function postHeight() {
  const height = document.getElementById("app").scrollHeight + 16;
  // NubeSDK autoresize listens for { type: "resize", height }
  window.parent.postMessage({ type: "resize", height }, "*");
}

// ── Error / loading helpers ────────────────────────────────────────────────
function showError(msg) {
  const el = document.getElementById("error-msg");
  el.textContent = msg;
  el.style.display = "block";
  postHeight();
}

function clearError() {
  document.getElementById("error-msg").style.display = "none";
}

function setLoading(on) {
  document.getElementById("loading").style.display = on ? "block" : "none";
  document.getElementById("submit-btn").disabled = on;
  document.getElementById("result-section").style.display = "none";
  clearError();
  postHeight();
}

// ── Toggle expanded/collapsed ──────────────────────────────────────────────
function expand() {
  isExpanded = true;
  document.getElementById("trigger-btn").style.display = "none";
  document.getElementById("widget-body").style.display = "block";

  if (garmentUrl) {
    const img = document.getElementById("garment-img");
    img.src = garmentUrl;
    img.style.display = "block";
    document.getElementById("garment-section").style.display = "block";
  }

  postHeight();
}

// ── Init from URL params ───────────────────────────────────────────────────
function init() {
  const params = new URLSearchParams(window.location.search);
  garmentUrl = params.get("garment_url") || null;
  category = params.get("category") || "tops";
  postHeight();
}

// Also accept init data via postMessage from NubeSDK parent
window.addEventListener("message", (e) => {
  if (!e.data || e.data.type !== "vton:init") return;
  garmentUrl = e.data.garment_url || garmentUrl;
  category = e.data.category || category;
});

// ── Trigger button ─────────────────────────────────────────────────────────
document.getElementById("trigger-btn").addEventListener("click", expand);

// ── Photo selection ────────────────────────────────────────────────────────
document.getElementById("person-input").addEventListener("change", (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  personFile = file;

  const preview = document.getElementById("preview-img");
  preview.src = URL.createObjectURL(file);
  preview.style.display = "block";

  clearError();
  postHeight();
});

// ── Submit ─────────────────────────────────────────────────────────────────
document.getElementById("submit-btn").addEventListener("click", async () => {
  if (!personFile) {
    showError("Por favor, escolha uma foto sua antes de continuar.");
    return;
  }
  if (!garmentUrl) {
    showError("Imagem do produto não encontrada. Tente recarregar a página.");
    return;
  }

  setLoading(true);

  try {
    const formData = new FormData();
    formData.append("person_image", personFile);
    formData.append("garment_url", garmentUrl); // backend fetches it server-side
    formData.append("category", category);

    const resp = await fetch(`${BACKEND_URL}/api/tryon`, {
      method: "POST",
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Erro no servidor (${resp.status})`);
    }

    const data = await resp.json();

    const resultSection = document.getElementById("result-section");
    const resultImg = document.getElementById("result-img");
    resultImg.src = data.result_url;
    resultImg.onload = () => {
      resultSection.style.display = "block";
      setLoading(false);
      postHeight();
    };
    resultImg.onerror = () => {
      setLoading(false);
      showError("Não foi possível exibir o resultado. Tente novamente.");
    };
  } catch (err) {
    setLoading(false);
    showError(err.message || "Algo deu errado. Por favor, tente novamente.");
  }
});

// ── Boot ───────────────────────────────────────────────────────────────────
init();
window.addEventListener("load", postHeight);
new ResizeObserver(postHeight).observe(document.getElementById("app"));
