import {
  init,
  AuthType,
  LiveboardEmbed,
  EmbedEvent,
} from "https://esm.sh/@thoughtspot/visual-embed-sdk@1.55.0";
import { config } from "./config.js";

const errorBox = document.getElementById("error");
function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

if (config.thoughtSpotHost.includes("YOUR-INSTANCE")) {
  showError("Set thoughtSpotHost in config.js before running the app.");
} else {
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
    // viz 2-4 so "Total Sales Amt by Zip Code" (viz 1) is not affected.
    isScopedLiveboardFilteringEnabled: true,
    isLiveboardCompactHeaderEnabled: true,
  });

  embed.on(EmbedEvent.Error, (e) => showError(`Embed error: ${JSON.stringify(e)}`));
  embed.render();
}
