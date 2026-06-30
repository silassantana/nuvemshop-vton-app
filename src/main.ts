import type { NubeSDK } from "@tiendanube/nube-sdk-types";
import { box, iframe, text } from "@tiendanube/nube-sdk-ui";

// Set VITE_WIDGET_URL env var before building (e.g. https://your-app.railway.app)
const WIDGET_BASE_URL: string = import.meta.env.VITE_WIDGET_URL ?? "https://PLACEHOLDER.railway.app";

export function App(nube: NubeSDK) {
  nube.on("page:loaded", (state) => {
    const page = state.location.page;

    if (page.type !== "product") return;

    const product = page.data.product;
    const garmentUrl = product.images[0]?.src ?? null;

    if (!garmentUrl) return;

    const category = inferCategory(product.tags);

    // Build iframe src with garment URL as query param so the widget
    // can read it on load (no postMessage needed for initial data).
    const widgetSrc = `${WIDGET_BASE_URL}/index.html?${new URLSearchParams({
      garment_url: garmentUrl,
      category,
    })}`;

    // Inject the widget iframe directly before the add-to-cart button.
    // The widget starts collapsed (just a "Experimentar" button) and
    // expands on user interaction — autoresize keeps the iframe height
    // in sync via { type: "resize", height } postMessages from the child.
    nube.render(
      "before_product_detail_add_to_cart",
      box({
        style: { display: "flex", flexDirection: "column", marginBottom: "12px" },
        children: [
          iframe({
            src: widgetSrc as `https://${string}`,
            width: "100%",
            // Start at button-only height; widget postMessages its real height
            height: "60px",
            autoresize: true,
            sandbox:
              "allow-scripts allow-same-origin allow-forms allow-popups allow-camera",
            style: { border: "none", borderRadius: "8px" },
          }),
        ],
      }),
    );
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function inferCategory(tags: string): "tops" | "bottoms" | "one-pieces" {
  const t = tags.toLowerCase();
  if (t.includes("calça") || t.includes("short") || t.includes("saia") || t.includes("bottom")) {
    return "bottoms";
  }
  if (t.includes("vestido") || t.includes("macacão") || t.includes("one-piece")) {
    return "one-pieces";
  }
  return "tops"; // default — most garments are tops
}
