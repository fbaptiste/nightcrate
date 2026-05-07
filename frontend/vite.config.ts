import basicSsl from "@vitejs/plugin-basic-ssl";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";
import { defineConfig } from "vite";

const lan = process.env.NIGHTCRATE_LAN === "1";

// Prefer mkcert-issued certs at frontend/.certs/{cert,key}.pem so iPads/iPhones
// with the local mkcert root CA installed get a fully-trusted connection (no
// browser warning, and Safari does not taint the canvas — pixel inspector
// works). Fall back to the in-process basicSsl plugin (untrusted self-signed
// cert) when no files are present.
const CERT_DIR = path.resolve(__dirname, ".certs");
const CERT_PATH = path.join(CERT_DIR, "cert.pem");
const KEY_PATH = path.join(CERT_DIR, "key.pem");
const haveCerts = fs.existsSync(CERT_PATH) && fs.existsSync(KEY_PATH);

export default defineConfig({
  plugins: [react(), ...(lan && !haveCerts ? [basicSsl()] : [])],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    open: !lan,
    host: lan ? "0.0.0.0" : "localhost",
    https:
      lan && haveCerts
        ? { cert: fs.readFileSync(CERT_PATH), key: fs.readFileSync(KEY_PATH) }
        : undefined,
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
