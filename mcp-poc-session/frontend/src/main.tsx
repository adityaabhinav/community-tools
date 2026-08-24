import { createRoot } from "react-dom/client";
import { init, AuthType, startAutoMCPFrameRenderer } from "@thoughtspot/visual-embed-sdk";
import App from "./App";

const orgId = import.meta.env.VITE_TS_ORG_ID as string;

init({
  thoughtSpotHost: import.meta.env.VITE_TS_HOST as string,
  authType: AuthType.TrustedAuthTokenCookieless,
  getAuthToken: async () => {
    const resp = await fetch("/ts-token");
    return resp.text();
  },
  ...(orgId ? { orgId } : {}),
});

startAutoMCPFrameRenderer({ frameParams: { height: "550px", width: "100%" } });

createRoot(document.getElementById("root")!).render(<App />);
