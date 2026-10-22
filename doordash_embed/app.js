import {
  init, LiveboardEmbed, AuthType, EmbedEvent,
} from "https://cdn.jsdelivr.net/npm/@thoughtspot/visual-embed-sdk/dist/tsembed.es.js";

const TS_HOST = "https://ps-internal.thoughtspot.cloud";
const LIVEBOARD_ID = "8930f905-38c0-4de3-b6ea-68bd9e275d93";

const FONT = `"DM Sans", "TT Norms Pro", -apple-system, "Helvetica Neue", Arial, sans-serif`;
const DD_RED = "#eb1700";

const statusEl = document.getElementById("status");
const showError = (msg) => { statusEl.textContent = msg; statusEl.className = "status error"; };

init({
  thoughtSpotHost: TS_HOST,
  // Passthrough: the user signs in to ThoughtSpot in the iframe (or uses an existing session).
  // For production, switch to AuthType.TrustedAuthTokenCookieless with your token endpoint.
  authType: AuthType.None,
  customizations: {
    style: {
      customCSSUrl: new URL("liveboard-theme.css", window.location.href).href,
      customCSS: {
        variables: {
          // Typography
          "--ts-var-root-font-family": FONT,
          "--ts-var-viz-title-font-family": FONT,
          "--ts-var-viz-description-font-family": FONT,
          "--ts-var-axis-title-font-family": FONT,
          "--ts-var-axis-data-label-font-family": FONT,
          "--ts-var-button--primary--font-family": FONT,
          "--ts-var-button--secondary--font-family": FONT,
          "--ts-var-button--tertiary--font-family": FONT,
          "--ts-var-chip-title-font-family": FONT,
          "--ts-var-liveboard-tab-font-family": FONT,
          "--ts-var-button-font-weight": "500",
          "--ts-var-liveboard-tab-font-weight": "500",
          "--ts-var-liveboard-tab-selected-font-weight": "700",
          "--ts-var-liveboard-group-title-font-weight": "700",
          "--ts-var-liveboard-group-tile-title-font-weight": "700",

          // DoorDash-like look
          "--ts-var-root-background": "#f7f7f7",
          "--ts-var-root-color": "#191919",
          "--ts-var-viz-title-color": "#191919",
          "--ts-var-viz-description-color": "#767676",
          "--ts-var-viz-background": "#ffffff",
          "--ts-var-viz-border-radius": "16px",
          "--ts-var-viz-box-shadow": "0 1px 3px rgba(0,0,0,0.08)",
          "--ts-var-liveboard-header-background": "#ffffff",
          "--ts-var-liveboard-header-font-color": "#191919",
          "--ts-var-button--primary-background": DD_RED,
          "--ts-var-button--primary--hover-background": "#c01300",
          "--ts-var-button--primary--active-background": "#a01000",
          "--ts-var-liveboard-tab-active-border-color": DD_RED,
          "--ts-var-liveboard-tab-selected-color": DD_RED,
          "--ts-var-liveboard-tab-border-radius": "999px",
        },
      },
    },
  },
});

const embed = new LiveboardEmbed(document.getElementById("ts-embed"), {
  frameParams: { width: "100%", height: "100%" },
  liveboardId: LIVEBOARD_ID,
  fullHeight: false,
});

embed
  .on(EmbedEvent.Load, () => statusEl.classList.add("hidden"))
  .on(EmbedEvent.Error, (e) => { console.error(e); showError("Couldn't load insights. Please try again."); });

embed.render().catch((e) => { console.error(e); showError(String(e?.message || e)); });
