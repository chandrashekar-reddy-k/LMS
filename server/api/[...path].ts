/**
 * Same-origin gateway to the FastAPI backend.
 *
 * The browser only ever talks to this site, so the API's HttpOnly session cookies are
 * first-party cookies for this domain. We also pass the visitor's real IP (proven with a
 * shared secret) so the API's rate limits apply per visitor, not per proxy.
 */
import { getRequestIP, proxyRequest } from 'h3'

export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event)
  const rawOrigin = (config.apiOrigin || process.env.VITE_API_URL || process.env.NUXT_API_ORIGIN || 'http://127.0.0.1:8000') as string
  // Strip trailing slash and trailing '/api' to avoid duplicate /api in target URL
  const base = rawOrigin.replace(/\/$/, '').replace(/\/api$/, '')
  const target = base + event.path // event.path keeps /api/... and the query
  const headers: Record<string, string> = {}
  const proxySecret = config.proxySecret || process.env.NUXT_PROXY_SECRET || ''
  if (proxySecret) {
    headers['x-lh-proxy-secret'] = proxySecret
    headers['x-lh-client-ip'] = getRequestIP(event, { xForwardedFor: true }) || ''
  }
  return proxyRequest(event, target, { headers })
})
