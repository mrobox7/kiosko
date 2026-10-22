import { createReadStream, readFileSync } from 'node:fs'
import { join } from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// The browser VAD loads its worklet, model and WebAssembly runtime by URL, as plain files.
// Vite's dev server refuses to serve JavaScript from public/ as a module, so serve them from
// node_modules under /vad/ ourselves, and emit the same files into the production build.
const VAD_FILES: Record<string, { from: string; type: string }> = {
  'vad.worklet.bundle.min.js': { from: '@ricky0123/vad-web/dist', type: 'text/javascript' },
  'silero_vad_v5.onnx': { from: '@ricky0123/vad-web/dist', type: 'application/octet-stream' },
  'ort-wasm-simd-threaded.mjs': { from: 'onnxruntime-web/dist', type: 'text/javascript' },
  'ort-wasm-simd-threaded.wasm': { from: 'onnxruntime-web/dist', type: 'application/wasm' },
}

function vadAssets(): Plugin {
  let root = process.cwd()
  const path = (name: string) => join(root, 'node_modules', VAD_FILES[name].from, name)
  return {
    name: 'vad-assets',
    configResolved(config) {
      root = config.root
    },
    configureServer(server) {
      server.middlewares.use('/vad', (req, res, next) => {
        const name = decodeURIComponent((req.url ?? '').split('?')[0].replace(/^\//, ''))
        if (!(name in VAD_FILES)) return next()
        res.setHeader('Content-Type', VAD_FILES[name].type)
        createReadStream(path(name)).pipe(res)
      })
    },
    generateBundle() {
      for (const name of Object.keys(VAD_FILES))
        this.emitFile({ type: 'asset', fileName: `vad/${name}`, source: readFileSync(path(name)) })
    },
  }
}

// The dev server forwards /api to the Python API and /images to the ordering server that holds
// the dish pictures, so the browser sees one origin.
export default defineConfig({
  plugins: [react(), tailwindcss(), vadAssets()],
  server: {
    proxy: {
      '/api': { target: process.env.API_URL ?? 'http://localhost:8001', ws: true },
      '/images': { target: process.env.BACKEND_URL ?? 'http://localhost:8010' },
    },
  },
})
