# Docker Production Deployment Guide

This guide explains how to deploy the ICT Agent API using the pre-built Docker image `kamilzafar/ict_agent`.

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- `.env` file with your API keys
- At least 4GB RAM available
- Port 8009 available (or configure different port)

### 2. Setup

```bash
# Copy production docker-compose file
cp docker-compose.prod.yml.example docker-compose.prod.yml

# Create .env file from example
cp .env.example .env

# Edit .env and add your API keys
nano .env
```

### 3. Deploy

```bash
# Start the service
docker-compose -f docker-compose.prod.yml up -d

# Check logs
docker-compose -f docker-compose.prod.yml logs -f

# Check status
docker-compose -f docker-compose.prod.yml ps
```

## Configuration

### Environment Variables

All configuration is done through environment variables in your `.env` file. See `.env.example` for all available options.

**Required:**
- `OPENAI_API_KEY` - Your OpenAI API key

**Recommended for Production:**
- `WORKERS=4` - Number of worker processes
- `ENVIRONMENT=production` - Production mode
- `CORS_ORIGINS` - Specific allowed origins (not *)
- `TRUSTED_HOSTS` - Specific trusted hosts (not *)
- `LOG_LEVEL=info` - Appropriate log level

### Resource Limits

The production compose file includes resource limits:
- **CPU**: 2-4 cores
- **Memory**: 4-8GB RAM

Adjust in `docker-compose.prod.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 8G
```

## Image Versions

### Using Latest Version
```yaml
image: kamilzafar/ict_agent:latest
```

### Using Specific Version (Recommended for Production)
```yaml
image: kamilzafar/ict_agent:v1.0.0
```

## Volume Mounts

### Memory Database
The memory database is persisted in `./memory_db`:
```yaml
volumes:
  - ./memory_db:/app/memory_db
```

**Important:** Backup this directory regularly!

### Logs (Optional)
If you want to persist logs:
```yaml
volumes:
  - ./logs:/app/logs
```

## Health Checks

The container includes health checks:
- Checks `/health` endpoint every 30 seconds
- 120 second timeout
- 3 retries before marking unhealthy
- 40 second startup grace period

## Monitoring

### View Logs
```bash
# Follow logs
docker-compose -f docker-compose.prod.yml logs -f

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail=100

# Specific service
docker-compose -f docker-compose.prod.yml logs api
```

### Check Health
```bash
# Container health
docker-compose -f docker-compose.prod.yml ps

# API health endpoint
curl http://localhost:8009/health
```

### Resource Usage
```bash
# Container stats
docker stats ict_agent_api
```

## Updates

### Update to Latest Version
```bash
# Pull latest image
docker-compose -f docker-compose.prod.yml pull

# Restart with new image
docker-compose -f docker-compose.prod.yml up -d
```

### Rollback to Previous Version
```bash
# Edit docker-compose.prod.yml to use specific version
# Then restart
docker-compose -f docker-compose.prod.yml up -d
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs

# Check environment variables
docker-compose -f docker-compose.prod.yml config
```

### Port Already in Use
```bash
# Change port in docker-compose.prod.yml
ports:
  - "8010:8009"  # Use different host port

# Or find and kill process using port 8009
```

### Out of Memory
```bash
# Increase memory limits in docker-compose.prod.yml
deploy:
  resources:
    limits:
      memory: 16G  # Increase as needed
```

### Database Issues
```bash
# Check volume mount
docker-compose -f docker-compose.prod.yml exec api ls -la /app/memory_db

# Backup database
cp -r ./memory_db ./memory_db.backup
```

## Production Checklist

- [ ] `.env` file configured with API keys
- [ ] Resource limits adjusted for your server
- [ ] Port configured correctly
- [ ] Volume mounts configured
- [ ] Health checks enabled
- [ ] Logging configured
- [ ] CORS origins set (not *)
- [ ] Trusted hosts set (not *)
- [ ] Nginx proxy configured (if using)
- [ ] Backup strategy for `memory_db`
- [ ] Monitoring set up
- [ ] SSL/TLS configured (via nginx)

## Scaling

### Horizontal Scaling (Multiple Containers)

```yaml
services:
  api:
    image: kamilzafar/ict_agent:latest
    deploy:
      replicas: 3  # Run 3 instances
    # ... rest of config
```

**Note:** Each container needs its own port or use a load balancer.

### Vertical Scaling (More Resources)

Increase resource limits in `docker-compose.prod.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '8'
      memory: 16G
```

## Backup & Recovery

### Backup Memory Database
```bash
# Stop container
docker-compose -f docker-compose.prod.yml stop

# Backup
tar -czf memory_db_backup_$(date +%Y%m%d).tar.gz ./memory_db

# Start container
docker-compose -f docker-compose.prod.yml start
```

### Restore Memory Database
```bash
# Stop container
docker-compose -f docker-compose.prod.yml stop

# Restore
tar -xzf memory_db_backup_YYYYMMDD.tar.gz

# Start container
docker-compose -f docker-compose.prod.yml start
```

## Security Best Practices

1. **Never commit `.env` file** - It contains sensitive API keys
2. **Use specific CORS origins** - Don't use `*` in production
3. **Set trusted hosts** - Don't use `*` in production
4. **Use specific image versions** - Avoid `latest` tag in production
5. **Limit resource usage** - Set appropriate limits
6. **Regular updates** - Keep Docker image updated
7. **Network isolation** - Use custom networks
8. **SSL/TLS** - Always use HTTPS via nginx

## Example Production Setup

```bash
# 1. Create production directory
mkdir -p /opt/ict_agent
cd /opt/ict_agent

# 2. Copy files
cp docker-compose.prod.yml.example docker-compose.prod.yml
cp .env.example .env

# 3. Configure
nano .env  # Add API keys

# 4. Deploy
docker-compose -f docker-compose.prod.yml up -d

# 5. Verify
curl http://localhost:8009/health
```

## Support

For issues or questions:
- Check logs: `docker-compose -f docker-compose.prod.yml logs`
- Check health: `curl http://localhost:8009/health`
- Review documentation in `docs/` directory

