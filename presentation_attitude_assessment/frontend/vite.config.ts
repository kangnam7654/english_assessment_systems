import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/ui/",
  server: {
    host: "127.0.0.1",
    port: 43188,
    strictPort: true,
    proxy: {
      "/jobs": "http://127.0.0.1:43187",
      "/health": "http://127.0.0.1:43187",
      "/docs": "http://127.0.0.1:43187",
      "/openapi.json": "http://127.0.0.1:43187",
    },
  },
});
