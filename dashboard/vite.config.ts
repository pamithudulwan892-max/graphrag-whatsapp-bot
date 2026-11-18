import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, forward API calls to the FastAPI server on port 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/webhooks": "http://127.0.0.1:8000",
    },
  },
});
