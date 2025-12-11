# Nginx Proxy Setup Guide

This guide explains how to configure nginx as a reverse proxy for the ICT Agent API.

## Overview

The application is configured to work behind an nginx reverse proxy with:
- Proxy header support (X-Forwarded-*)
- Trusted host validation
- CORS configuration
- Rate limiting support
- SSL/TLS termination

## Quick Setup

### 1. Install Nginx

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# CentOS/RHEL
sudo yum install nginx
```

### 2. Copy Configuration

```bash
# Copy the example configuration
sudo cp nginx/nginx.conf.example /etc/nginx/sites-available/ict-agent

# Or use the main configuration
sudo cp nginx/nginx.conf /etc/nginx/sites-available/ict-agent
```

### 3. Edit Configuration

Edit `/etc/nginx/sites-available/ict-agent`:

```nginx
# Update server_name
server_name api.your-domain.com;

# Update upstream if using different port
server 127.0.0.1:8009;
```

### 4. Enable Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/ict-agent /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## Configuration Options

### Environment Variables

Set these in your `.env` file or docker-compose.yml:

```bash
# Root path for subpath proxying (e.g., /api)
ROOT_PATH=/api

# Trusted hosts (comma-separated)
TRUSTED_HOSTS=api.your-domain.com,www.your-domain.com

# CORS origins
CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com
```

### Subpath Proxying

If you want to proxy to a subpath (e.g., `https://your-domain.com/api/`):

**Nginx config:**
```nginx
location /api/ {
    proxy_pass http://fastapi_backend/;
    # Note the trailing slash
}
```

**Environment variable:**
```bash
ROOT_PATH=/api
```

### SSL/TLS Setup

1. **Using Let's Encrypt (Recommended):**

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d api.your-domain.com

# Auto-renewal
sudo certbot renew --dry-run
```

2. **Manual SSL:**

Update nginx config:
```nginx
listen 443 ssl http2;
ssl_certificate /path/to/certificate.crt;
ssl_certificate_key /path/to/private.key;
```

### Rate Limiting

The nginx config includes rate limiting:
- **100 requests per minute** per IP
- **10 concurrent connections** per IP
- Burst of 20 requests allowed

Adjust in `nginx.conf`:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
limit_conn_zone $binary_remote_addr zone=api_conn:10m;
```

## Testing

### 1. Test Health Endpoint

```bash
curl http://api.your-domain.com/health
```

### 2. Test API Endpoint

```bash
curl -X POST http://api.your-domain.com/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "message": "Hello"
  }'
```

### 3. Test with SSL

```bash
curl https://api.your-domain.com/health
```

## Troubleshooting

### Check Nginx Logs

```bash
# Access logs
sudo tail -f /var/log/nginx/ict_agent_access.log

# Error logs
sudo tail -f /var/log/nginx/ict_agent_error.log
```

### Common Issues

1. **502 Bad Gateway**
   - Check if FastAPI is running: `curl http://localhost:8009/health`
   - Verify upstream server in nginx config

2. **CORS Errors**
   - Check `CORS_ORIGINS` environment variable
   - Verify nginx is forwarding headers correctly

3. **404 Not Found**
   - Check `ROOT_PATH` matches nginx location
   - Verify proxy_pass has correct trailing slash

4. **Connection Timeout**
   - Increase timeout values in nginx config
   - Check firewall rules

## Production Checklist

- [ ] SSL/TLS certificate installed
- [ ] Rate limiting configured
- [ ] Trusted hosts set
- [ ] CORS origins configured
- [ ] Logging configured
- [ ] Health check endpoint accessible
- [ ] Firewall rules configured
- [ ] Monitoring set up

## Security Recommendations

1. **Use HTTPS** - Always use SSL/TLS in production
2. **Set Trusted Hosts** - Restrict allowed hosts
3. **Configure CORS** - Only allow specific origins
4. **Enable Rate Limiting** - Prevent abuse
5. **Use Firewall** - Restrict access to nginx port only
6. **Regular Updates** - Keep nginx updated

## Example: Full Production Setup

```nginx
upstream fastapi_backend {
    least_conn;
    server 127.0.0.1:8009 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name api.your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Proxy settings
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    location /health {
        proxy_pass http://fastapi_backend;
    }
    
    location / {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://fastapi_backend;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name api.your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

