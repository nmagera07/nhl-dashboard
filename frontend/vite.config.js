import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Makes the site installable ("Add to Home Screen") and opens it
    // full-screen like an app. The service worker precaches the app shell
    // (JS/CSS/HTML/icons) so it launches instantly; API calls always go to
    // the network, since scores and standings must never be served stale.
    VitePWA({
      // Prompt, not autoUpdate: a downloaded release waits for the user to
      // tap Refresh in UpdateBanner, instead of appearing only after the
      // installed app is closed and reopened.
      registerType: 'prompt',
      includeAssets: ['icon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'PuckPulse',
        short_name: 'PuckPulse',
        description: 'Live NHL scores, playoff odds, goal alerts, and an AI hockey analyst.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#0a0b0f',
        theme_color: '#0a0b0f',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          // Same art; the glyph sits inside the safe zone, so it survives
          // Android's circle/squircle masks.
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}'],
        navigateFallback: '/index.html',
        cleanupOutdatedCaches: true,
        // Goal/final push notifications (public/push-sw.js).
        importScripts: ['push-sw.js'],
      },
    }),
  ],
  test: {
    environment: 'jsdom',
    alias: { 'virtual:pwa-register/react': '/src/test/pwaRegisterStub.js' },
    setupFiles: './src/test/setup.js',
    globals: true,
  },
})
