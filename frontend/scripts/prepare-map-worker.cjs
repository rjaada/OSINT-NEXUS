const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..')
const target = path.join(root, 'public', 'maplibre')
fs.mkdirSync(target, { recursive: true })
for (const file of ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs']) {
  fs.copyFileSync(path.join(root, 'node_modules', 'maplibre-gl', 'dist', file), path.join(target, file))
}
