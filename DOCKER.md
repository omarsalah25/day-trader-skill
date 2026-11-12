# Day Trader 24/7 - Docker Server Deployment Guide

This guide covers deploying the **Day Trader 24/7 Autonomous Market Terminal & Execution Pipeline** to any remote Linux server, VPS (AWS EC2, DigitalOcean, Hetzner, GCP, Linode), or local Docker host.

---

## 1. Quick Start with Docker Compose (Recommended)

Docker Compose is the fastest way to run the 24/7 engine on your server with automatic restarts and persistent data storage.

### Step 1: Clone or Copy Repository
```bash
git clone https://github.com/Jakeschincariol/day-trader-skill.git
cd day-trader-skill
```

### Step 2: Launch Container in Detached Mode
```bash
docker compose up -d --build
```

### Step 3: View Live Streaming Logs
```bash
docker compose logs -f day-trader
```

### Step 4: Open Dashboard in Your Browser
Visit:
```
http://<YOUR-SERVER-IP>:8080
```

---

## 2. Standalone Docker CLI Deployment

If you prefer using pure Docker without compose:

### Build the Docker Image
```bash
docker build -t day-trader-24-7 .
```

### Run the Container
```bash
docker run -d \
  --name day-trader-24-7 \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/trader:/app/trader \
  -e TZ=America/New_York \
  -e SEC_USER_AGENT="DayTraderAdmin admin@example.com" \
  day-trader-24-7
```

### Container Management Commands
- **Check Status & Health**:
  ```bash
  docker ps
  ```
- **Inspect Live Trading Output**:
  ```bash
  docker logs -f day-trader-24-7
  ```
- **Stop Container**:
  ```bash
  docker stop day-trader-24-7
  ```
- **Restart Container**:
  ```bash
  docker restart day-trader-24-7
  ```

---

## 3. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8080` | Port for the HTTP web server and REST API. |
| `PYTHONUNBUFFERED` | `1` | Forces real-time unbuffered log output to `docker logs`. |
| `TZ` | `America/New_York` | Timezone for NYSE trading sessions (9:30 AM - 4:00 PM ET). |
| `SEC_USER_AGENT` | `DayTraderServer admin@example.com` | User Agent for SEC EDGAR regulatory and 8-K filings. |
| `ALPACA_API_KEY` | *(empty)* | Optional: Alpaca Paper or Live REST API Key ID. |
| `ALPACA_SECRET_KEY` | *(empty)* | Optional: Alpaca Paper or Live REST API Secret Key. |

> **Note on Broker Credentials**: You can pass `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` via environment variables, or enter them directly inside the dashboard UI under the **Settings & Risk Rules** tab.

---

## 4. Persistent Data Storage (`/app/trader`)

All trading configurations, active positions, order histories, transactions, and scan data are stored in `/app/trader`.

By mounting the host directory `./trader:/app/trader`:
1. Your portfolio and trade history persist safely across container updates and server reboots.
2. You can back up your trading data simply by archiving the `./trader` directory:
   ```bash
   tar -czvf trader_backup_$(date +%F).tar.gz trader/
   ```

---

## 5. Production Server Best Practices

### Firewall Configuration (Ubuntu / Debian UFW)
Allow traffic on port 8080:
```bash
sudo ufw allow 8080/tcp
sudo ufw reload
```

### Production Nginx Reverse Proxy with HTTPS (SSL)
For secure public access with SSL via Let's Encrypt:

```nginx
server {
    server_name trader.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable SSL using Certbot:
```bash
sudo certbot --nginx -d trader.yourdomain.com
```

### Healthcheck Monitoring
The Docker image includes an automatic healthcheck:
```bash
curl -f http://localhost:8080/api/status
```
Returns HTTP 200 with JSON payload containing 24/7 engine state, active positions, and AI agent status.
