import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Forward API calls to the FastAPI backend during development.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
