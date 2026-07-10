import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In sviluppo (npm run dev) il frontend gira su :5173 e inoltra le chiamate
// /api e /videos al backend su :8000. In produzione, dopo `npm run build`,
// il backend serve direttamente i file buildati, quindi il proxy non serve.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/videos": "http://localhost:8000",
    },
  },
});
