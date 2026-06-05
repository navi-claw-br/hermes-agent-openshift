# Hermes Agent on OpenShift

Deploy [Hermes Agent](https://github.com/NousResearch/hermes-agent) — the self-improving AI agent with a built-in learning loop — on Red Hat OpenShift.

> Based on the guide: [Deploy Hermes Agent on OpenShift AI with vLLM model serving](https://developers.redhat.com/articles/2026/06/02/deploy-hermes-agent-openshift-ai-vllm-model-serving)
>
> This version deploys **Hermes Agent only** (no vLLM). The agent connects to your own LLM endpoint (OpenAI, Anthropic, or any OpenAI-compatible API).

## Architecture

```
┌─────────────────────────────────┐
│     OpenShift Cluster           │
│  ┌─────────────────────────┐    │
│  │  Hermes Agent Pod       │    │
│  │  ┌───────────────────┐  │    │
│  │  │ Gateway HTTP      │  │    │
│  │  │ Port 8080         │  │    │
│  │  │ GET  /health      │  │    │
│  │  │ POST /api         │  │    │
│  │  │ POST /telegram    │  │    │
│  │  │ POST /discord     │  │    │
│  │  └────────┬──────────┘  │    │
│  │           │              │    │
│  │  ┌────────▼──────────┐  │    │
│  │  │ Agent Core        │  │    │
│  │  │ - Skills          │  │    │
│  │  │ - Memory (Honcho) │  │    │
│  │  │ - Cron scheduler  │  │    │
│  │  └────────┬──────────┘  │    │
│  │           │              │    │
│  │  ┌────────▼──────────┐  │    │
│  │  │ Persistent Volume │  │    │
│  │  │ 10Gi gp3-csi      │  │    │
│  │  │ SQLite + Skills   │  │    │
│  │  └───────────────────┘  │    │
│  └─────────────────────────┘    │
│                                  │
│  LLM Provider ──────────────────►│
│  (OpenAI / Anthropic / Custom)   │
└─────────────────────────────────┘
         │
    OpenShift Route (TLS)
         │
    Telegram / Discord / HTTP Clients
```

## Prerequisites

- OpenShift 4.x cluster (any platform — this works on AWS, bare metal, etc.)
- `oc` CLI authenticated with cluster admin privileges
- LLM API key (OpenAI, Anthropic, or any OpenAI-compatible provider)

## Quick Start

```bash
# 1. Clone this repository
git clone https://github.com/navi-claw-br/hermes-agent-openshift.git
cd hermes-agent-openshift

# 2. Create namespace and resources
oc apply -k manifests/

# 3. Configure your LLM API key
oc create secret generic hermes-secrets \
  --from-literal=OPENAI_API_KEY=sk-your-key-here \
  -n hermes

# 4. (Optional) Configure a different LLM provider
oc set env deployment/hermes-agent \
  OPENAI_BASE_URL=https://api.openai.com/v1 \
  LLM_MODEL=gpt-4o \
  -n hermes

# 5. Wait for the pod to be ready
oc get pods -n hermes -w
```

## Configuration

### ConfigMap (`03-hermes-config.yaml`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API endpoint |
| `LLM_MODEL` | `gpt-4o` | Model name to use |
| `GATEWAY_PORT` | `8080` | HTTP gateway port |
| `GATEWAY_ALLOW_ALL_USERS` | `true` | Allow all users access |

### Secrets (create via `oc create secret`)

| Secret Key | Description |
|------------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (or your provider's key) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (for Telegram integration) |
| `DISCORD_BOT_TOKEN` | Discord bot token (for Discord integration) |

### LLM Providers

**OpenAI:**
```bash
oc create secret generic hermes-secrets \
  --from-literal=OPENAI_API_KEY=sk-... \
  -n hermes
```

**Anthropic:**
```bash
oc create secret generic hermes-secrets \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  -n hermes

oc set env deployment/hermes-agent \
  LLM_PROVIDER=anthropic \
  LLM_MODEL=claude-sonnet-4-20250514 \
  -n hermes
```

**Custom OpenAI-compatible (e.g., local vLLM, Groq, Together):**
```bash
oc set env deployment/hermes-agent \
  OPENAI_BASE_URL=https://api.groq.com/openai/v1 \
  LLM_MODEL=llama3-70b-8192 \
  -n hermes
```

## Verification

```bash
# Check pod status
oc get pods -n hermes
NAME                           READY   STATUS    RESTARTS   AGE
hermes-agent-7d9f8b5c6d-xk2p9  1/1    Running   0          2m

# Test health endpoint (from inside the cluster)
oc run test-hermes --rm -i --image=curlimages/curl -- \
  curl -s http://hermes-agent.hermes.svc.cluster.local:8080/health
# Expected: {"status":"healthy","gateway":"running"}

# Get external URL (if Route is deployed)
oc get route hermes-agent -n hermes -o jsonpath='https://{.spec.host}'
```

## Interacting with Hermes

### HTTP API
```bash
AGENT_URL=https://$(oc get route hermes-agent -n hermes -o jsonpath='{.spec.host}')

curl -X POST "$AGENT_URL/api" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello! What can you do?",
    "user_id": "my-user",
    "platform": "api"
  }'
```

### Direct Shell Access
```bash
POD=$(oc get pods -n hermes -l app.kubernetes.io/name=hermes-agent -o jsonpath='{.items[0].metadata.name}')
oc exec -it "$POD" -n hermes -- /opt/hermes/venv/bin/python -m hermes_cli.main
```

## Telegram Integration

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Get your bot token
3. Configure the secret:
```bash
oc create secret generic hermes-secrets \
  --from-literal=TELEGRAM_BOT_TOKEN=your-bot-token \
  -n hermes \
  --dry-run=client -o yaml | oc apply -f -
```
4. Restart the deployment:
```bash
oc rollout restart deployment/hermes-agent -n hermes
```
5. Set the webhook:
```bash
WEBHOOK_URL=$(oc get route hermes-agent -n hermes -o jsonpath='{.spec.host}')
curl -X POST "https://api.telegram.org/bot<your-bot-token>/setWebhook?url=https://$WEBHOOK_URL/telegram"
```

## Discord Integration

1. Create a Discord application and bot at https://discord.com/developers
2. Get the bot token
3. Configure the secret:
```bash
oc create secret generic hermes-secrets \
  --from-literal=DISCORD_BOT_TOKEN=your-token \
  -n hermes \
  --dry-run=client -o yaml | oc apply -f -
```
4. Restart the deployment
5. Invite the bot to your server using the OAuth2 URL generator

## Building Your Own Image

If you want to build a custom Hermes Agent image:

```bash
git clone https://github.com/NousResearch/hermes-agent
cd hermes-agent

# Build the UBI 9 container image
podman build -f Dockerfile.ubi \
  -t quay.io/your-org/hermes-agent:latest \
  --platform linux/amd64 .

podman push quay.io/your-org/hermes-agent:latest

# Update manifests/04-hermes-deployment.yaml with your image
sed -i 's|image: quay.io/aicatalyst/hermes-agent:latest|image: quay.io/your-org/hermes-agent:latest|' manifests/04-hermes-deployment.yaml

oc apply -k manifests/
```

## Persistent Storage

Hermes Agent stores all state in `/opt/data` (mounted via PVC):

- **SQLite database**: Full conversation history with FTS5 search
- **Skills registry**: Reusable skills generated by the learning loop
- **User models**: Honcho dialectic memory per user
- **Cron schedules**: Scheduled autonomous tasks

The default PVC is 10Gi with `gp3-csi` (AWS EBS). Adjust in `02-hermes-storage.yaml`:

```yaml
resources:
  requests:
    storage: 50Gi  # Increase for more history
```

## Scaling and Updates

```bash
# Scale down/up
oc scale deployment/hermes-agent -n hermes --replicas=0
oc scale deployment/hermes-agent -n hermes --replicas=1

# Edit environment variables
oc set env deployment/hermes-agent LLM_MODEL=gpt-4o-mini -n hermes

# View logs
oc logs -n hermes deployment/hermes-agent --tail=50 -f

# Restart
oc rollout restart deployment/hermes-agent -n hermes
```

## Uninstall

```bash
oc delete namespace hermes
# Or selectively:
oc delete -k manifests/
```

## Related

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) — Official repository
- [Deploy Hermes Agent on OpenShift AI with vLLM](https://developers.redhat.com/articles/2026/06/02/deploy-hermes-agent-openshift-ai-vllm-model-serving) — Original guide (includes vLLM)
- [Hermes OpenShift (with vLLM)](https://github.com/aicatalyst-team/hermes-openshift) — Full deployment with GPU model serving
