# SLIM Guessing Game - Educational AI Demo

An educational demo showcasing **AI Agents** and **SLIM's secure messaging** for children. Watch AI agents play "20 Questions" together!

> **Purpose**: This is a demonstration application created to teach children about AI agents and secure communication using the [SLIM platform](https://docs.agntcy.org/messaging/slim-core/).

## The Game

AI agents play "20 Questions" - one agent thinks of an object, others ask questions to guess it!

### The Players (AI Agents)

1. **Coordinator** - Game master (manages rules and turns)
2. **Alice (Thinker)** - Thinks of a secret object and answers yes/no questions
3. **Bob, Carol, Dave (Guessers)** - Ask questions and try to guess the object
4. **Travis (Observer)** - Watches the game and translates messages to other languages

### How They Communicate

```
┌─────────────────────────────────────────────────────────────────────┐
│                   PUBLIC GROUP SESSION (Broadcast)                  │
│                                                                     │
│  Coordinator ◄──► Alice ◄──► Bob ◄──► Carol ◄──► Dave ◄──► Travis   │
│                                                                     │
│  All game communication: questions, answers, guesses, game state    │
│  Everyone sees everything on this channel                           │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│              SECRET 1:1 SESSION (Private, Encrypted)                │
│                                                                     │
│              Alice ──────────────────────► Travis                   │
│                     "Crayon" (secret)                               │
│                                                                     │
│  Only Alice and Travis participate in this channel                  │
│  MLS encrypted - Coordinator, Bob, Carol, Dave cannot see it        │
│  Used for observability/monitoring without affecting game           │
└─────────────────────────────────────────────────────────────────────┘
```

**Two channels running at the same time:**
- **Public channel**: Everyone talks about the game
- **Secret channel**: Alice secretly tells Travis the answer (for monitoring)

## Quick Start

Want to run this? See the **[Quick Start Guide](QUICKSTART.md)** for detailed setup instructions.

**TL;DR:**
```bash
# 1. Install prerequisites: Docker, Kind, Task, Helm, and an LLM provider
# 2. Configure LLM credentials
cp deployments/.env.example deployments/.env
# Edit deployments/.env with your LLM settings

# 3. Start everything
task setup

# 4. Watch the game
task game:logs

# 5. Stop everything
task teardown
```

## What Children Learn

This demo teaches:
- **AI Agents** - How AI programs work together
- **Secure Communication** - How messages can be private or public
- **Strategic Thinking** - Different ways to solve problems
- **Natural Language** - How AI understands questions

## Useful Commands

See [QUICKSTART.md](QUICKSTART.md) for full commands and troubleshooting.

```bash
task game:logs     # Watch the game
task game:status   # Check status
task game:restart  # Restart game
task teardown      # Stop everything
```

## Technical Details

Built with:
- **[SLIM Platform](https://github.com/agntcy/slim)** - Secure agent messaging (MLS encryption)
- **[SLIM Docs](https://docs.agntcy.org/messaging/slim-core/)** 
- **Python 3.11** - Agent logic
- **Kubernetes/Docker/Kind** - Container orchestration
- **LLM** - AI intelligence (OpenAI, Azure, or local Ollama)

Demonstrates:
- **Dual-session architecture** - Public broadcast + private 1:1 channels
- **MLS encryption** - End-to-end secure messaging
- **AI agent collaboration** - Multiple agents working together
- **Turn-based coordination** - Managing sequential interactions

For detailed implementation, see the [`src/guessing_game/`](https://github.com/lgecse/slim-demo/tree/main/src/guessing_game) source code.

## License

Apache 2.0 - see LICENSE file 
