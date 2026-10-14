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

  const { init, AuthType, Action, LiveboardEmbed, EmbedEvent } = await import(SDK_URL);

  // AuthType.None relies on the user already being logged in to ThoughtSpot in
  // this browser. Switch to SSO or trusted auth for production.
  init({
    thoughtSpotHost: config.thoughtSpotHost,
    authType: AuthType.None,
  });

  const grid = document.getElementById("viz-grid");

  const rule = new URLSearchParams(location.search).get("rule") || config.filterRule;
  const keepsFilter = (viz) => {
    if (config.hideCrossFilterEverywhere) return false;
    return rule === "vizId" ? config.filterVizIds.includes(viz.id) : viz.showFilter;
  };
  document.title = `Retail Sales (rule: ${rule})`;

  for (const viz of config.vizzes) {
    const card = document.createElement("section");
    card.className = "card";
    const title = document.createElement("h2");
    title.textContent = viz.title;
    const container = document.createElement("div");
    container.className = "viz";
    card.append(title, container);
    grid.append(card);

    const embed = new LiveboardEmbed(container, {
      frameParams: { width: "100%", height: "100%" },
      liveboardId: config.liveboardId,
      vizId: viz.id,
      // hiddenActions removes the item from the menu (disabledActions would grey it out).
      // It applies per embed, which is why each viz has its own embed.
      hiddenActions: keepsFilter(viz) ? [] : [Action.CrossFilter],
    });

    embed.on(EmbedEvent.Error, (e) => showError(`Embed error: ${JSON.stringify(e)}`));
    embed.on(EmbedEvent.AuthExpire, () => showError("Session expired. Log in to ThoughtSpot and reload."));
    embed.render();
  }
}

main().catch((e) => showError(`Failed to start: ${e && e.message ? e.message : e}`));
