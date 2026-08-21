# Deployment — Docker, Kubernetes, Production

> **Take Alcyoneus OS from development to production.**

---

## Quick Start

```bash
# 1. Install with production extras
pip install "alcyoneus[google-genai,openai,mcp,pg_checkpoint,qdrant,redis,kafka,otel]"

# 2. Set environment variables
cp .env.example .env
# Edit .env with your credentials

# 3. Run
python -m myapp.server
```

---

## Environment Variables

```bash
# LLM Providers
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
VERTEX_AI_PROJECT=my-project
VERTEX_AI_LOCATION=us-central1
ANTHROPIC_API_KEY=...

# Persistence
POSTGRES_CONN_STR=postgresql://user:pass@host:5432/db
REDIS_URL=redis://localhost:6379/0

# Vector Store
QDRANT_URL=https://cluster.qdrant.io
QDRANT_API_KEY=...
MEM0_API_KEY=...

# Observability
SENTRY_DSN=https://...
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel:4317

# Messaging
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672

# Security
SENTRY_DSN=...
VAULT_ADDR=https://vault:8200
```

---

## Docker

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import alcyoneus; print('OK')" || exit 1

CMD ["python", "-m", "myapp.server"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_CONN_STR=postgresql://postgres:postgres@db:5432/alcyoneus
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
    depends_on:
      - db
      - redis
      - qdrant
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: alcyoneus
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:v1.8
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
  redisdata:
  qdrant_data:
```

---

## Kubernetes (Helm)

### Install

```bash
helm repo add alcyoneus https://charts.alcyoneus.ai
helm install alcyoneus alcyoneus/alcyoneus \
  --namespace alcyoneus \
  --create-namespace \
  --set image.repository=myregistry/alcyoneus \
  --set image.tag=v1.0.1 \
  --set postgresql.enabled=true \
  --set redis.enabled=true \
  --set qdrant.enabled=true
```

### values.yaml (Production)

```yaml
image:
  repository: myregistry/alcyoneus
  tag: v1.0.1
  pullPolicy: IfNotPresent

replicas: 3

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 500m
    memory: 1Gi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
  targetCPUUtilization: 70

env:
  - name: OPENAI_API_KEY
    valueFrom:
      secretKeyRef:
        name: alcyoneus-secrets
        key: OPENAI_API_KEY

postgresql:
  enabled: true
  auth:
    existingSecret: alcyoneus-postgres-secret

redis:
  enabled: true
  auth:
    existingSecret: alcyoneus-redis-secret

qdrant:
  enabled: true
  service:
    type: ClusterIP

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: alcyoneus.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: alcyoneus-tls
      hosts:
        - alcyoneus.example.com

monitoring:
  prometheus:
    enabled: true
    serviceMonitor:
      enabled: true
  grafana:
    enabled: true
    dashboards:
      alcyoneus:
        url: https://grafana.example.com/d/alcyoneus
```

---

## Monitoring

### Prometheus Metrics

```python
from alcyoneus.runtime.observability import setup_metrics

# Auto-instruments with Prometheus
setup_metrics(
    service_name="alcyoneus-app",
    port=9090,
)
```

### Metrics Exposed

| Metric | Type | Description |
|--------|------|-------------|
| `alcyoneus_requests_total` | Counter | Total requests by method/endpoint/status |
| `alcyoneus_request_duration_seconds` | Histogram | Request latency |
| `alcyoneus_active_sessions` | Gauge | Active sessions |
| `alcyoneus_tool_calls_total` | Counter | Tool calls by tool/status |
| `alcyoneus_checkpoint_duration_seconds` | Histogram | Checkpoint save/load time |

### Grafana Dashboard

```json
{
  "title": "Alcyoneus OS",
  "panels": [
    {"title": "Requests/sec", "targets": [{"expr": "rate(alcyoneus_requests_total[5m])"}]},
    {"title": "Latency p95", "targets": [{"expr": "histogram_quantile(0.95, rate(alcyoneus_request_duration_seconds_bucket[5m]))"}]},
    {"title": "Active Sessions", "targets": [{"expr": "alcyoneus_active_sessions"}]},
    {"title": "Tool Calls", "targets": [{"expr": "rate(alcyoneus_tool_calls_total[5m])"}]},
    {"title": "Checkpoint Latency", "targets": [{"expr": "histogram_quantile(0.95, rate(alcyoneus_checkpoint_duration_seconds_bucket[5m]))"}]}
  ]
}
```

---

## 4. Logging

```python
import logging
from alcyoneus.utils.logging import setup_logging

# JSON structured logging with trace context
setup_logging(
    level="INFO",
    format="json",
    include_trace=True,
)

logger = logging.getLogger("myapp")
logger.info("Order processed", extra={"order_id": "123", "user_id": "456"})
```

---

## 5. Secrets Management

### Vault

```python
import hvac

client = hvac.Client(url="https://vault:8200", token="...")
secret = client.secrets.kv.v2.read_secret_version(path="alcyoneus/prod")
OPENAI_API_KEY = secret["data"]["data"]["OPENAI_API_KEY"]
```

### AWS Secrets Manager

```python
import boto3

client = boto3.client("secretsmanager", region_name="us-east-1")
secret = client.get_secret_value(SecretId="alcyoneus/prod")
config = json.loads(secret["SecretString"])
```

### Kubernetes Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: alcyoneus-secrets
type: Opaque
stringData:
  OPENAI_API_KEY: "sk-..."
  POSTGRES_CONN_STR: "postgresql://..."
  QDRANT_API_KEY: "..."
```

```yaml
# In deployment
envFrom:
  - secretRef:
      name: alcyoneus-secrets
```

---

## 6. CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: pip install -e ".[test]"
      - run: pytest tests/ -q --cov=alcyoneus

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: myregistry/alcyoneus:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: azure/k8s-set-context@v1
      - run: helm upgrade --install alcyoneus ./deployment/helm/alcyoneus \
          --set image.tag=${{ github.sha }} \
          --namespace production
```

---

## 5. Health Checks

```python
from fastapi import FastAPI
from alcyoneus.storage.checkpointer import PgCheckpointer

app = FastAPI()

@app.get("/health")
async def health():
    checks = {
        "status": "healthy",
        "checks": {}
    }
    
    # Database
    try:
        await checkpointer.health_check()
        checks["checks"]["database"] = "healthy"
    except Exception as e:
        checks["checks"]["database"] = f"unhealthy: {e}"
        checks["status"] = "degraded"
    
    # Redis
    try:
        await redis.ping()
        checks["checks"]["redis"] = "healthy"
    except Exception as e:
        checks["checks"]["redis"] = f"unhealthy: {e}"
        checks["status"] = "degraded"
    
    # Qdrant
    try:
        await qdrant.get_collections()
        checks["checks"]["qdrant"] = "healthy"
    except Exception as e:
        checks["checks"]["qdrant"] = f"unhealthy: {e}"
        checks["status"] = "degraded"
    
    return checks
```

---

## 6. Rollback Strategy

```bash
# Quick rollback
helm rollback alcyoneus 1

# Or with kubectl
kubectl rollout undo deployment/alcyoneus -n alcyoneus

# Blue-green
kubectl apply -f deployment/blue.yaml
# verify
kubectl patch service alcyoneus -p '{"spec":{"selector":{"version":"blue"}}}'
```

---

## 6. Backup Strategy

```bash
# PostgreSQL backup
pg_dump -h $DB_HOST -U $DB_USER $DB_NAME > backup_$(date +%Y%m%d).sql

# Qdrant snapshot
curl -X POST "https://$QDRANT_URL/snapshots" \
  -H "api-key: $QDRANT_API_KEY"

# Redis backup
redis-cli --rdb /backup/redis_$(date +%Y%m%d).rdb
```

---

## 7. Scaling

| Component | Strategy |
|-----------|----------|
| API pods | HPA (CPU > 70%) |
| Workers | KEDA (queue length) |
| PostgreSQL | Read replicas + PgBouncer |
| Redis | Cluster mode |
| Qdrant | Cluster mode |

---

## 6. Troubleshooting

| Issue | Check |
|-------|-------|
| High latency | Check checkpoint latency, DB indexes |
| OOM kills | Increase memory limits, check memory leaks |
| Checkpoint timeouts | Increase `shutdown_timeout`, check DB |
| Tool timeouts | Increase tool timeouts in policy |
| WebSocket drops | Check proxy timeouts, keepalive |