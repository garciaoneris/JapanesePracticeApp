import { svelte } from '@sveltejs/vite-plugin-svelte';
import { VitePWA } from 'vite-plugin-pwa';
import { defineConfig } from 'vite';

// GitHub Pages serves at https://<user>.github.io/JapanesePracticeApp/
// so assets and the service-worker scope must live under that subpath.
// Override via APP_BASE=/ for a custom root domain.
const base = process.env.APP_BASE ?? '/JapanesePracticeApp/';

export default defineConfig({
  base,
  plugins: [
    svelte(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,webmanifest,json}'],
        // bundle.json is ~15 MB with the full N5–N1 curriculum; bump the
        // Workbox default (2 MB) cap so it precaches in full. 20 MB leaves
        // a little headroom for future vocabulary additions without needing
        // to retouch this config every release.
        maximumFileSizeToCacheInBytes: 20 * 1024 * 1024,
        navigateFallback: `${base}index.html`,
      },
      manifest: {
        name: 'Japanese Practice',
        short_name: 'JP Practice',
        description: 'Practice Japanese kanji and vocabulary with stroke order, TTS, and STT.',
        theme_color: '#1b1b1f',
        background_color: '#1b1b1f',
        display: 'standalone',
        orientation: 'any',
        start_url: base,
        scope: base,
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
});
