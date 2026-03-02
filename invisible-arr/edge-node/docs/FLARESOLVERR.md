# FlareSolverr

## What It Does

FlareSolverr is a proxy server that solves Cloudflare and DDoS-GUARD challenges. Some torrent indexers use Cloudflare protection, which prevents Prowlarr from scraping them directly. FlareSolverr runs a headless browser to solve these challenges and pass the results back to Prowlarr.

## How It Works

1. FlareSolverr runs as a container in the stack (port 8191 internally)
2. Prowlarr sends requests through FlareSolverr when configured
3. FlareSolverr solves the Cloudflare challenge using a headless Chrome instance
4. The resolved cookies/headers are returned to Prowlarr

## Configuration in Prowlarr

### Step 1: Add FlareSolverr as an Indexer Proxy

1. In Prowlarr, go to **Settings > Indexers**
2. Click the **+** under "Indexer Proxies"
3. Select **FlareSolverr**
4. Set the URL to: `http://flaresolverr:8191`
5. Set Request Timeout to `60` seconds
6. Save

### Step 2: Enable Per-Indexer

Not all indexers need FlareSolverr. Only enable it for indexers that are Cloudflare-protected:

1. Go to **Indexers** in Prowlarr
2. Edit the specific indexer that requires Cloudflare bypass
3. Under **Advanced Settings**, select the FlareSolverr proxy
4. Test the indexer to verify it works

## Healthcheck

FlareSolverr includes a health endpoint. The Docker Compose config includes:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8191"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## Timeout Settings

- **Default timeout:** 60 seconds per request
- **Max timeout:** 120 seconds (for very slow challenges)
- Configure via `CAPTCHA_SOLVER` environment variable (default: `none`)

## Troubleshooting

- **High memory usage:** FlareSolverr runs Chrome. Expect ~300-500MB RAM usage.
- **Slow responses:** First request after startup is slower (Chrome cold start). Subsequent requests are faster.
- **Challenge failures:** Some sites rotate their challenges frequently. If an indexer consistently fails, it may have added additional bot detection.
