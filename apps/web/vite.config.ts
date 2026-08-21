import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: new URL(".", import.meta.url).pathname,
  base: process.env.GITHUB_PAGES === "true" ? "/Engram-Memory/" : "/",
  plugins: [react()],
  build: {
    outDir: "../../dist-web",
    emptyOutDir: true,
  },
});
