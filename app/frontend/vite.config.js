import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/chat": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/version": "http://localhost:8000",
      "/metrics": "http://localhost:8000",
    },
  },
});
