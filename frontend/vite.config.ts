import basicSsl from "@vitejs/plugin-basic-ssl";
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

const lan = process.env.NIGHTCRATE_LAN === "1";

export default defineConfig({
  plugins: [react(), ...(lan ? [basicSsl()] : [])],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    open: !lan,
    host: lan ? "0.0.0.0" : "localhost",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        secure: false,
      },
      "/docs": {
        target: "http://127.0.0.1:8000",
        secure: false,
      },
      "/openapi.json": {
        target: "http://127.0.0.1:8000",
        secure: false,
      },
    },
  },
});
