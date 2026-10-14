import { config } from "./config.js";

const SDK_URL = "https://esm.sh/@thoughtspot/visual-embed-sdk@1.53.1";

const errorBox = document.getElementById("error");
function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

async function main() {
  if (config.thoughtSpotHost.includes("YOUR-INSTANCE")) {
    showError("Set thoughtSpotHost in config.js before running the app.");
    return;
  }

  const { init, AuthType, LiveboardEmbed, EmbedEvent } = await import(SDK_URL);

  // AuthType.None relies on the user already being logged in to ThoughtSpot in
  // this browser. Switch to SSO or trusted auth for production.
  init({
    thoughtSpotHost: config.thoughtSpotHost,
    authType: AuthType.None,
  });

  const embed = new LiveboardEmbed("#ts-embed", {
    frameParams: { width: "100%", height: "100%" },
    liveboardId: config.liveboardId,

    // Lets filters be scoped to a group of visualizations (SDK 1.53.0+,
    // ThoughtSpot 26.10.0.cl+). In the liveboard, scope the filter to
    // the 4th viz only so vizzes 1-3 are not affected.
    isScopedLiveboardFilteringEnabled: true,
    isLiveboardCompactHeaderEnabled: true,
  });

  embed.on(EmbedEvent.Error, (e) => showError(`Embed error: ${JSON.stringify(e)}`));
  embed.on(EmbedEvent.AuthExpire, () => showError("Session expired. Log in to ThoughtSpot and reload."));
  await embed.render();
}

main().catch((e) => showError(`Failed to start: ${e && e.message ? e.message : e}`));
