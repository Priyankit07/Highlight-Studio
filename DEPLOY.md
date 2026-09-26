# Deployment Guide: Football Highlight Studio

This guide details how to deploy **Football Highlight Studio** for a hackathon demonstration or self-hosted production.

---

## ⚠️ Important Hosting Assumptions (Not Serverless)

> [!CAUTION]
> **Do NOT deploy this application to serverless platforms** (e.g. Vercel, AWS Lambda, Cloudflare Workers, or Google Cloud Run scale-to-zero).
>
> 1. **Compute & Encoding:** Audio excitement detection and video clip cutting with FFmpeg require substantial multi-core CPU power and sustained memory.
> 2. **Persistent Local Disk:** Chunked upload assembly, raw video storage, intermediate envelopes, proxies, and highlight reel renders require several gigabytes of fast persistent disk (minimum 20 GB recommended).
> 3. **Long-Running Operations:** Full-match video extraction and H.264 video rendering run as isolated background processes that exceed serverless execution time limits (which typically terminate after 15–60 seconds).
> 4. **Live Progress Streaming:** The studio relies on Server-Sent Events (SSE) for sub-second stage updates and logs, requiring unbuffered HTTP connections.

---

## Option A: Single Linux VM with Caddy (Recommended)

A standard cloud VM (e.g. Hetzner, DigitalOcean Droplet, AWS EC2 t3.xlarge, or Linode) running Ubuntu 22.04/24.04 LTS.

### 1. Prerequisites
- Docker Engine & Docker Compose v2:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  ```
- Caddy Server (for automatic Let's Encrypt HTTPS and HTTP/2):
  ```bash
  sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
  sudo apt update
  sudo apt install caddy
  ```

### 2. Clone and Configure
```bash
git clone https://github.com/your-org/highlight-generator.git /opt/highlight-studio
cd /opt/highlight-studio
cp .env.example .env
```

Edit `.env` for your demo deployment:
```ini
APP_ENV=demo
DEMO_PASSWORD=hackathon-judge-2026
MAX_UPLOAD_GB=1
MAX_CONCURRENT_JOBS=1
RETENTION_DAYS=1
ENABLE_URL_IMPORT=false
CORS_ORIGIN=https://highlights.yourdomain.com
PORT=8000
```

### 3. Start Containerized Application
```bash
docker compose up -d --build
```

### 4. Configure Caddy Reverse Proxy
Edit `/etc/caddy/Caddyfile`:

```caddyfile
highlights.yourdomain.com {
    # Match client body size to support 8 MB upload chunks
    request_body {
        max_size 25MB
    }

    # Reverse proxy to Docker container on port 8000
    reverse_proxy 127.0.0.1:8000 {
        # CRITICAL for SSE: disable response buffering so live job events stream immediately
        flush_interval -1

        # Long read timeouts for video encoding operations
        transport http {
            read_timeout 600s
            response_header_timeout 600s
        }
    }
}
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```

---

## Option B: Local Machine Behind Cloudflare Tunnel

To demo directly from a local workstation or MacBook:

### 1. Install cloudflared
```bash
brew install cloudflare/cloudflare/cloudflared
cloudflared tunnel login
```

### 2. Create and Route Tunnel
```bash
cloudflared tunnel create highlight-studio
cloudflared tunnel route dns highlight-studio demo.yourdomain.com
```

### 3. Configure Tunnel
Create `~/.cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /Users/<user>/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: demo.yourdomain.com
    service: http://localhost:8000
    originRequest:
      noChunkedEncoding: false
      connectTimeout: 30s
      originServerName: demo.yourdomain.com
  - service: http_status:404
```

### 4. Run Tunnel and Local Server
```bash
# Terminal 1: Run application
APP_ENV=demo DEMO_PASSWORD=secret uv run uvicorn api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Run tunnel
cloudflared tunnel run highlight-studio
```

---

## Alternative: Nginx Reverse Proxy Configuration

If using Nginx instead of Caddy:
```nginx
server {
    server_name highlights.yourdomain.com;

    # Allow 8 MB chunk uploads
    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CRITICAL: Disable proxy buffering for Server-Sent Events (SSE)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;

        # Enable HTTP/1.1 for keepalive connections
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

---

## Verification & Smoke Test

Verify the deployment end-to-end using the automated smoke test script:
```bash
./scripts/smoke_test.sh https://highlights.yourdomain.com
```

The smoke test validates:
1. Health endpoint response and status.
2. Direct 60s sample clip download.
3. Chunked upload of the test video.
4. Reel processing completion.
5. Highlight MP4 download and playable video validation (duration > 0).
