# Quick Start Guide

Get the SLIM Guessing Game running in 5 minutes!

## Prerequisites

Install these tools first:
- [Docker Desktop](https://docs.docker.com/desktop/)
- [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [Helm](https://helm.sh/docs/intro/install/)
- [Task](https://taskfile.dev/installation/)
- `envsubst` - Install via: `brew install gettext` (macOS) or `apt-get install gettext-base` (Linux)

## Setup Steps

### 1. Clone and Navigate
```bash
git clone git@github.com:lgecse/slim-demo.git
cd slim-demo
```

### 2. Configure LLM
Copy the template and edit with your LLM details:
```bash
cp deployments/.env.example deployments/.env
```

Then edit `deployments/.env`:

**For OpenAI:**
```bash
LLM_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-key-here
LLM_MODEL=gpt-4o
```

**For Local Ollama (if installed):**
```bash
LLM_URL=http://ollama.default.svc.cluster.local:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5:0.5b
```

### 3. Deploy Everything
```bash
task setup
```

This will:
- Create a local Kubernetes cluster
- Install SLIM messaging platform
- Deploy the game agents
- Start the game

### 4. Watch the Game
```bash
task game:logs
```

## Common Commands

```bash
# Check status
task game:status

# Restart game
task game:restart

# Stop everything
task teardown

# View all commands
task --list
```

## Troubleshooting

**Pods not starting?**
```bash
kubectl get pods --all-namespaces
kubectl describe pod <pod-name>
```

**SLIM not connecting?**
```bash
task slim:status
task slim:logs
```

**Need to rebuild?**
```bash
task build
task game:restart
```

## Next Steps

- Read [README.md](README.md) for project overview and architecture
- Explore the `src/guessing_game/` source code
- Check out the [SLIM documentation](https://docs.agntcy.org/messaging/slim-core/)

## Getting Help

- Check existing [GitHub Issues](https://github.com/lgecse/slim-demo/issues)
- Review the [SLIM repo](https://github.com/agntcy/slim)
- Open a new issue if you're stuck

Have fun watching the AI agents play! 

