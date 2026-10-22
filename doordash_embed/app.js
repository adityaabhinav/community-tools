import {
  init, LiveboardEmbed, AuthType, EmbedEvent,
} from "https://cdn.jsdelivr.net/npm/@thoughtspot/visual-embed-sdk/dist/tsembed.es.js";

const TS_HOST = "https://ps-internal.thoughtspot.cloud";

// DoorDash uses proprietary "TT Norms Pro"; DM Sans is a close free stand-in.
const DOORDASH_FONT = `"DM Sans", "TT Norms Pro", -apple-system, "Helvetica Neue", Arial, sans-serif`;
// Stand-ins for Deliveroo (ROO) and Wolt; replace with the licensed brand fonts in each theme CSS.
const ROO_FONT = `"Outfit", "Roobert", -apple-system, "Helvetica Neue", Arial, sans-serif`;
const WOLT_FONT = `"Nunito", "Omnes", -apple-system, "Helvetica Neue", Arial, sans-serif`;
// Facebook uses the system UI font stack (SF Pro on Apple, Segoe UI on Windows, Roboto on Android).
const FACEBOOK_FONT = `system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`;

// Build the font-related CSS variables once per theme.
const themeVariables = (font, accent, accentHover, accentActive, pageBg) => ({
  // Typography
  "--ts-var-root-font-family": font,
  "--ts-var-viz-title-font-family": font,
  "--ts-var-viz-description-font-family": font,
  "--ts-var-axis-title-font-family": font,
  "--ts-var-axis-data-label-font-family": font,
  "--ts-var-button--primary--font-family": font,
  "--ts-var-button--secondary--font-family": font,
  "--ts-var-button--tertiary--font-family": font,
  "--ts-var-chip-title-font-family": font,
  "--ts-var-liveboard-tab-font-family": font,
  "--ts-var-button-font-weight": "600",
  "--ts-var-liveboard-tab-font-weight": "500",
  "--ts-var-liveboard-tab-selected-font-weight": "700",
  "--ts-var-liveboard-group-title-font-weight": "700",
  "--ts-var-liveboard-group-tile-title-font-weight": "700",
  // Look and feel
  "--ts-var-root-background": pageBg,
  "--ts-var-root-color": "#191919",
  "--ts-var-viz-title-color": "#191919",
  "--ts-var-viz-description-color": "#767676",
  "--ts-var-viz-background": "#ffffff",
  "--ts-var-viz-box-shadow": "0 1px 3px rgba(0,0,0,0.08)",
  "--ts-var-liveboard-header-background": "#ffffff",
  "--ts-var-liveboard-header-font-color": "#191919",
  "--ts-var-button--primary-background": accent,
  "--ts-var-button--primary--hover-background": accentHover,
  "--ts-var-button--primary--active-background": accentActive,
  "--ts-var-liveboard-tab-active-border-color": accent,
  "--ts-var-liveboard-tab-selected-color": accent,
});

const VIEWS = {
  doordash: {
    liveboardId: "8930f905-38c0-4de3-b6ea-68bd9e275d93",
    cssFile: "liveboard-theme.css",
    variables: {
      ...themeVariables(DOORDASH_FONT, "#eb1700", "#c01300", "#a01000", "#f7f7f7"),
      "--ts-var-viz-border-radius": "16px",
      "--ts-var-liveboard-tab-border-radius": "999px",
    },
  },
  // TODO: set the real liveboard IDs for ROO and WOLT (currently reuse the second liveboard).
  roo: {
    liveboardId: "5a328046-8a29-4c11-ad85-52cfdf685005",
    cssFile: "liveboard-theme-roo.css",
    variables: {
      ...themeVariables(ROO_FONT, "#00ccbc", "#00b3a5", "#009a8e", "#f9fafa"),
      "--ts-var-viz-border-radius": "12px",
      "--ts-var-liveboard-tab-border-radius": "999px",
    },
  },
  wolt: {
    liveboardId: "5a328046-8a29-4c11-ad85-52cfdf685005",
    cssFile: "liveboard-theme-wolt.css",
    variables: {
      ...themeVariables(WOLT_FONT, "#009de0", "#008ac7", "#0077ae", "#f5f7f9"),
      "--ts-var-viz-border-radius": "12px",
      "--ts-var-liveboard-tab-border-radius": "999px",
    },
  },
  facebook: {
    liveboardId: "5a328046-8a29-4c11-ad85-52cfdf685005",
    cssFile: "liveboard-theme-facebook.css",
    variables: {
      ...themeVariables(FACEBOOK_FONT, "#1877f2", "#166fe5", "#1462cc", "#f0f2f5"),
      "--ts-var-viz-border-radius": "8px",
      "--ts-var-liveboard-tab-border-radius": "6px",
    },
  },
};

const statusEl = document.getElementById("status");
const hostEl = document.getElementById("ts-embed");
const tabs = document.querySelectorAll("[data-view]");

const showStatus = (msg, isError = false) => {
  statusEl.textContent = msg;
  statusEl.className = "status" + (isError ? " error" : "");
};

// Global init: auth only. Styles are passed per embed so each tab can use its own theme.
// Passthrough: the user signs in to ThoughtSpot in the iframe (or uses an existing session).
// For production, switch to AuthType.TrustedAuthTokenCookieless with your token endpoint.
init({ thoughtSpotHost: TS_HOST, authType: AuthType.None });

let current = null;
let embed = null;

function show(name) {
  const view = VIEWS[name];
  if (!view || name === current) return;
  current = name;
  tabs.forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  document.body.dataset.theme = name;
  showStatus("Loading your insights\u2026");

  if (embed) { embed.destroy(); embed = null; }
  hostEl.innerHTML = "";

  embed = new LiveboardEmbed(hostEl, {
    frameParams: { width: "100%", height: "100%" },
    liveboardId: view.liveboardId,
    fullHeight: false,
    customizations: {
      style: {
        customCSSUrl: new URL(view.cssFile, window.location.href).href,
        customCSS: { variables: view.variables },
      },
    },
  });

  const mine = embed;
  mine
    .on(EmbedEvent.Load, () => { if (embed === mine) statusEl.classList.add("hidden"); })
    .on(EmbedEvent.Error, (e) => { console.error(e); if (embed === mine) showStatus("Couldn't load insights. Please try again.", true); });
  mine.render().catch((e) => { console.error(e); if (embed === mine) showStatus(String(e?.message || e), true); });
}

tabs.forEach((t) => t.addEventListener("click", (ev) => { ev.preventDefault(); show(t.dataset.view); }));
show(new URLSearchParams(location.search).get("view") in VIEWS ? new URLSearchParams(location.search).get("view") : "doordash");
