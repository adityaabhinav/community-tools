import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "../", "");
  return {
  plugins: [react()],
  define: {
    "import.meta.env.VITE_TS_HOST": JSON.stringify(env.TS_HOST),
    "import.meta.env.VITE_TS_ORG_ID": JSON.stringify(env.TS_ORG_ID ?? ""),
    "import.meta.env.VITE_TS_WORKSHEET_ID": JSON.stringify(env.TS_WORKSHEET_ID ?? ""),
  },
  server: {
    port: 5184,
    strictPort: true,
    proxy: {
      "/chat": "http://localhost:8080",
      "/models": "http://localhost:8080",
      "/history": "http://localhost:8080",
      "/token": "http://localhost:8080",
      "/ts-token": "http://localhost:8080",
      "/health": "http://localhost:8080",
    },
  },
  };
});
