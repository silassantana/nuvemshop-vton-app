import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "src/main.ts",
      name: "App",
      fileName: "main",
      formats: ["es"],
    },
    rollupOptions: {
      // nube-sdk-ui is bundled in — NubeSDK apps are single-file bundles
      external: [],
    },
  },
});
