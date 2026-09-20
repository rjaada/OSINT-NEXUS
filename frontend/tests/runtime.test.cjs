const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
const { NextRequest } = require('next/server')
function load(file, globals = {}) {
  const source = fs.readFileSync(require('node:path').join(__dirname, '..', file), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  vm.runInNewContext(code, { exports, require, process: { env: {} }, URL, AbortSignal, ...globals })
  return exports
}
test('forged UI cookies cannot grant access', async () => {
  const { proxy } = load('proxy.ts')
  const response = await proxy(new NextRequest('https://nexus.test/v2/admin', { headers: { cookie: 'osint_session=1; osint_role=admin' } }))
  assert.equal(new URL(response.headers.get('location')).pathname, '/login')
})
test('backend outage fails closed even with an auth token', async () => {
  const { proxy } = load('proxy.ts', { fetch: async () => { throw Error('offline') } })
  const response = await proxy(new NextRequest('https://nexus.test/v2/admin', { headers: { cookie: 'osint_auth=forged; osint_role=admin' } }))
  assert.equal(new URL(response.headers.get('location')).pathname, '/login')
})
test('backend role overrides forged admin cookie', async () => {
  const { proxy } = load('proxy.ts', { fetch: async () => ({ ok: true, json: async () => ({ authenticated: true, role: 'viewer' }) }) })
  const response = await proxy(new NextRequest('https://nexus.test/v2/admin', { headers: { cookie: 'osint_auth=valid; osint_role=admin' } }))
  assert.equal(new URL(response.headers.get('location')).search, '?access=admin_denied')
})
test('verified admin can open admin page', async () => {
  const { proxy } = load('proxy.ts', { fetch: async () => ({ ok: true, json: async () => ({ authenticated: true, role: 'admin' }) }) })
  const response = await proxy(new NextRequest('https://nexus.test/v2/admin', { headers: { cookie: 'osint_auth=valid' } }))
  assert.equal(response.headers.get('x-middleware-next'), '1')
})
test('HTTPS deployment uses secure same-origin websocket', () => {
  const api = load('lib/api.ts', { window: { location: { origin: 'https://nexus.test' } } })
  assert.equal(api.API_BASE, '')
  assert.equal(api.websocketBase(), 'wss://nexus.test')
})
test('explicit API deployment sets websocket host and trims trailing slash', () => {
  const api = load('lib/api.ts', { process: { env: { NEXT_PUBLIC_API_URL: 'https://api.nexus.test/' } }, window: { location: { origin: 'https://nexus.test' } } })
  assert.equal(api.API_BASE, 'https://api.nexus.test')
  assert.equal(api.websocketBase(), 'wss://api.nexus.test')
})
function pdfRoute(fetch) {
  return load('app/api/v2/briefs/pdf/route.ts', {
    fetch,
    require: (name) => {
      if (name === 'next/server') return require(name)
      if (name === 'playwright') return { chromium: { launch: () => { throw Error('Unauthorized browser launch') } } }
      return {}
    },
  })
}
test('PDF renderer rejects anonymous requests before starting Chromium', async () => {
  const { POST } = pdfRoute()
  const response = await POST(new NextRequest('https://nexus.test/api/v2/briefs/pdf', { method: 'POST' }))
  assert.equal(response.status, 401)
})
test('PDF renderer enforces CSRF', async () => {
  const { POST } = pdfRoute()
  const response = await POST(new NextRequest('https://nexus.test/api/v2/briefs/pdf', { method: 'POST', headers: { cookie: 'osint_auth=token' } }))
  assert.equal(response.status, 403)
})
test('PDF renderer rejects verified viewers before starting Chromium', async () => {
  const { POST } = pdfRoute(async () => ({ ok: true, json: async () => ({ authenticated: true, role: 'viewer' }) }))
  const response = await POST(new NextRequest('https://nexus.test/api/v2/briefs/pdf', { method: 'POST', headers: { cookie: 'osint_auth=token; osint_csrf=csrf', 'x-csrf-token': 'csrf' } }))
  assert.equal(response.status, 403)
})
