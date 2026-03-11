---
name: bunny-cdn
description: Manage bunny.net CDN for jroots.co via API. Configure pull zones, optimizer, origin shield, edge rules, cache purging, error pages, and security settings. Use when working with bunny.net, CDN configuration, cache management, or pull zone settings.
---

# Bunny.net CDN Management

## Authentication

- Base URL: `https://api.bunny.net`
- Auth header: `AccessKey: <api-key>`
- API key is stored in `.env.local` as `BUNNY_API_KEY` (gitignored, local only)
- Dashboard: https://dash.bunny.net/account/api-keys

## jroots.co Pull Zone

| Property | Value |
|----------|-------|
| Pull Zone ID | `5460677` |
| Name | `jroots` |
| Origin | `https://jroots.co` |
| CDN hostname | `jroots.b-cdn.net` |

### Current settings

- **Optimizer**: enabled (WebP, CSS/JS minify, HTML Prerender, auto image optimization, image quality 85/70 desktop/mobile)
- **Origin Shield**: enabled, zone `FR` (France, closest to Coolify server)
- **Edge Rule**: "Security response headers" — X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy
- **Custom 404**: enabled, whitelabel, Russian language
- **Hotlink protection**: disabled (see Gotchas)

### CDN integration in codebase

| Layer | Config | Effect |
|-------|--------|--------|
| Frontend (Vite) | `base: process.env.CDN_BASE \|\| "/"` in `frontend/vite.config.ts` | Static JS/CSS/assets served from CDN |
| Frontend (Docker) | `ARG CDN_BASE` in `frontend/Dockerfile` | Build arg passed to Vite |
| Backend (FastAPI) | `cdn_base: str = ""` in `backend/app/config.py` | Thumbnail URLs prefixed with CDN |
| Docker Compose | `CDN_BASE: https://jroots.b-cdn.net` in `docker-compose.prod.yml` | Prod value for both services |
| Nginx | `Cache-Control: public, immutable` + 1y expiry for `/assets/` in `frontend/nginx.conf` | Aggressive caching for hashed Vite assets |

Note: frontend `CDN_BASE` uses trailing slash (`https://jroots.b-cdn.net/`), backend uses no trailing slash (`https://jroots.b-cdn.net`).

## API Operations

All examples use shell variables:

```bash
KEY="<api-key>"
ZONE=5460677
```

### List pull zones

```bash
curl -s -H "AccessKey: $KEY" "https://api.bunny.net/pullzone"
```

### Get pull zone details

```bash
curl -s -H "AccessKey: $KEY" "https://api.bunny.net/pullzone/$ZONE"
```

### Update pull zone settings

```bash
curl -s -X POST \
  -H "AccessKey: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"OptimizerEnabled": true, "EnableOriginShield": true}' \
  "https://api.bunny.net/pullzone/$ZONE"
```

Only include fields you want to change. Omitted fields are not modified.

### Purge entire zone cache

```bash
curl -s -X POST -H "AccessKey: $KEY" \
  "https://api.bunny.net/pullzone/$ZONE/purgeCache"
```

### Purge a single URL

```bash
curl -s -X POST -H "AccessKey: $KEY" \
  "https://api.bunny.net/purge?url=https://jroots.b-cdn.net/assets/index.js"
```

### Add/update edge rule

```bash
curl -s -X POST \
  -H "AccessKey: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "ActionType": 5,
    "ActionParameter1": "X-Custom-Header",
    "ActionParameter2": "value",
    "Triggers": [{"Type": 0, "PatternMatches": ["*"], "PatternMatchingType": 0}],
    "ExtraActions": [],
    "TriggerMatchingType": 0,
    "Description": "My edge rule",
    "Enabled": true
  }' \
  "https://api.bunny.net/pullzone/$ZONE/edgerules/addOrUpdate"
```

To update an existing rule, include `"Guid": "<rule-guid>"`.

### Delete edge rule

```bash
curl -s -X DELETE -H "AccessKey: $KEY" \
  "https://api.bunny.net/pullzone/$ZONE/edgerules/$RULE_GUID"
```

### Get statistics

```bash
curl -s -H "AccessKey: $KEY" \
  "https://api.bunny.net/statistics?pullZone=$ZONE&dateFrom=2026-03-01&dateTo=2026-03-12"
```

## Pull Zone Settings Reference

### Optimizer

| Field | Type | Description |
|-------|------|-------------|
| `OptimizerEnabled` | bool | Master toggle |
| `OptimizerEnableWebP` | bool | Auto WebP conversion |
| `OptimizerMinifyCSS` | bool | CSS minification |
| `OptimizerMinifyJavaScript` | bool | JS minification |
| `OptimizerPrerenderHtml` | bool | SEO prerender for SPAs |
| `OptimizerAutomaticOptimizationEnabled` | bool | Smart image sizing |
| `OptimizerImageQuality` | int (1-100) | Desktop image quality |
| `OptimizerMobileImageQuality` | int (1-100) | Mobile image quality |
| `OptimizerDesktopMaxWidth` | int (0-5000) | Max desktop image width |
| `OptimizerMobileMaxWidth` | int (0-5000) | Max mobile image width |
| `OptimizerEnableManipulationEngine` | bool | Dynamic image API via URL params |

### Origin Shield

| Field | Type | Description |
|-------|------|-------------|
| `EnableOriginShield` | bool | Route all cache misses through one PoP |
| `OriginShieldZoneCode` | string | Region code (e.g., `FR`, `DE`, `US`) |
| `OriginShieldEnableConcurrencyLimit` | bool | Limit concurrent origin requests |
| `OriginShieldMaxConcurrentRequests` | int | Max concurrent requests to origin |

### Error Page

| Field | Type | Description |
|-------|------|-------------|
| `ErrorPageEnableCustomCode` | bool | Enable custom error page HTML |
| `ErrorPageCustomCode` | string | Full HTML for error pages |
| `ErrorPageWhitelabel` | bool | Remove bunny.net branding |

### Security

| Field | Type | Description |
|-------|------|-------------|
| `AllowedReferrers` | string[] | Hotlink protection allow list (empty = disabled) |
| `BlockedReferrers` | string[] | Blocked referrer hostnames |

### Cache

| Field | Type | Description |
|-------|------|-------------|
| `CacheControlMaxAgeOverride` | int | Override origin cache-control (seconds) |
| `CacheErrorResponses` | bool | Cache 4xx/5xx responses |
| `EnableSmartCache` | bool | Only cache known static file types |

## Edge Rule Schema

### ActionType enum

| Value | Name | ActionParameter1 | ActionParameter2 |
|-------|------|-------------------|-------------------|
| 0 | ForceSSL | — | — |
| 1 | Redirect | Target URL | — |
| 3 | OverrideCacheTime | Seconds | — |
| 4 | BlockRequest | — | — |
| 5 | SetResponseHeader | Header name | Header value |
| 6 | SetRequestHeader | Header name | Header value |
| 16 | OverrideBrowserCacheTime | Seconds | — |

### Trigger Type enum

| Value | Name | PatternMatches example |
|-------|------|------------------------|
| 0 | Url | `["*/api/*"]`, `["*"]` |
| 1 | RequestHeader | — (use Parameter1 for header name) |
| 3 | UrlExtension | `[".js", ".css"]` |
| 4 | CountryCode | `["US", "DE"]` |
| 5 | RemoteIP | `["1.2.3.4"]` |

### Multi-action rules

Use `ExtraActions` to set multiple headers in one rule:

```json
{
  "ActionType": 5,
  "ActionParameter1": "X-Content-Type-Options",
  "ActionParameter2": "nosniff",
  "Triggers": [{"Type": 0, "PatternMatches": ["*"], "PatternMatchingType": 0}],
  "ExtraActions": [
    {"ActionType": 5, "ActionParameter1": "X-Frame-Options", "ActionParameter2": "DENY"},
    {"ActionType": 5, "ActionParameter1": "Referrer-Policy", "ActionParameter2": "strict-origin-when-cross-origin"}
  ],
  "TriggerMatchingType": 0,
  "Description": "Security headers",
  "Enabled": true
}
```

Edge rules require at least one Trigger. Use `PatternMatches: ["*"]` with Type 0 (Url) for match-all.

## DNS, Storage, and Other Services

For services beyond Pull Zones, consult the full docs index:

```bash
curl -s https://docs.bunny.net/llms.txt
```

Key API areas:

| Service | Base path | Docs |
|---------|-----------|------|
| Pull Zones | `/pullzone` | https://docs.bunny.net/api-reference/core/pull-zone |
| DNS Zones | `/dnszone` | https://docs.bunny.net/api-reference/core/dns-zone |
| Storage Zones | `/storagezone` | https://docs.bunny.net/api-reference/core/storage-zone |
| Storage Files | Separate API per zone | https://docs.bunny.net/api-reference/storage |
| Edge Scripting | `/compute/script` | https://docs.bunny.net/api-reference/scripting |
| Stream | `/library` | https://docs.bunny.net/api-reference/stream |
| Shield (WAF) | Via Shield API | https://docs.bunny.net/api-reference/shield |

OpenAPI spec: `https://core-api-public-docs.b-cdn.net/docs/v3/public.json`

## Gotchas

1. **Hotlink protection breaks SPAs**: Setting `AllowedReferrers` causes 403 on dynamically imported JS chunks. Browsers send cross-origin Referer headers that fail the referrer check. Don't enable for pull zones serving SPA code.

2. **Always purge after config changes**: After modifying security/caching settings, purge the zone cache. Stale cached responses (including cached 403s) persist until purged or expired.

3. **CDN_BASE trailing slash matters**: Vite's `base` config needs a trailing slash (`https://jroots.b-cdn.net/`). The backend `cdn_base` setting should NOT have a trailing slash since it's concatenated with `/api/...` paths.

4. **Origin Shield vs Perma-Cache**: These are mutually exclusive. Cannot enable both simultaneously.

5. **HTML Prerender for React SPAs**: `OptimizerPrerenderHtml` serves fully rendered HTML to search engines and social crawlers. Critical for SEO with client-side rendered apps. No code changes needed.

6. **Edge Rules need triggers**: The API rejects rules with empty `Triggers` array. Use `[{"Type": 0, "PatternMatches": ["*"], "PatternMatchingType": 0}]` to match all URLs.

7. **Optimizer has a monthly cost**: Enabling `OptimizerEnabled` adds a per-zone monthly fee. Check current pricing at https://docs.bunny.net/optimizer/pricing.
