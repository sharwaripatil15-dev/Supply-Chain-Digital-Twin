import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vendor chunks. The 3D stack (deck.gl + MapLibre) is matched by package path only, so nothing in the initial
// bundle depends on it and it stays lazy: it downloads the first time someone opens a 3D view.
const CHUNKS = [
  ['cytoscape', /node_modules[\\/](cytoscape|react-cytoscapejs)[\\/]/],
  ['recharts', /node_modules[\\/](recharts|d3-[^\\/]+|victory-vendor)[\\/]/],
  ['react', /node_modules[\\/](react|react-dom|scheduler)[\\/]/],
  ['maplibre', /node_modules[\\/](maplibre-gl|react-map-gl|@vis\.gl)[\\/]/],
  ['deckgl', /node_modules[\\/](@deck\.gl|@luma\.gl|@math\.gl|@loaders\.gl|@probe\.gl)[\\/]/],
]

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, strictPort: true },
  preview: { host: true, port: 5173 },
  build: {
    // maplibre (~1.1 MB) and deckgl (~0.9 MB) are lazy chunks used only by the 3D view.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Shared runtime helpers (dynamic-import preload, CJS interop) get their own tiny chunk; otherwise Rollup
          // may park them inside the deck.gl chunk and the initial bundle would have to download it.
          if (/vite\/preload-helper|commonjsHelpers/.test(id)) return 'runtime'
          for (const [name, re] of CHUNKS) if (re.test(id)) return name
          return undefined
        },
      },
    },
  },
})
