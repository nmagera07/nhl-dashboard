# NHL Intelligence

> Moved here from `atelier-ai-labs/nhl-intelligence` in October 2026; its
> commit history came along via `git subtree`. Part of the NHL Dashboard
> repo so API and chat changes ship together.

A standalone, grounded conversational layer for the NHL Dashboard. It reads structured data from the dashboard public API, so it never receives dashboard database credentials.

## Phase 1

- Player, team, and standings questions
- Evidence labels showing which dashboard data was used
- No game recap claims until Phase 2 adds game-level data

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8001
```

Configure AI providers in `.env` (see `.env.example`). The service tries
them in order (`AI_PROVIDERS`, default `gemini,groq,cloudflare,ollama`) and
falls back to the next on a rate limit, outage, or bad key, so it runs on
free tiers. Use keys with no payment method attached. For local development,
Ollama on your own GPU works with no limits:

```bash
ollama pull qwen2.5:7b
OLLAMA_CONTEXT_LENGTH=8192 ollama serve   # then OLLAMA_BASE_URL=http://localhost:11434/v1
```

Ollama's default context window is 4,096 tokens and it silently drops the
*start* of longer prompts (including the instructions). The league context
is ~3.4K tokens (measured), so the default works, but 8,192 leaves room.
A 7B model is fine for development but inconsistent on multi-row questions
("who leads the league?" was right in one run and wrong in the next); use
the larger hosted models in production.

Keys are used only by this service and must never be sent to the browser.
Answers report which provider responded (`model` in the response).

## Deploy

Deployed to the `nhl-intelligence` Azure Container App (same environment as
the dashboard API; scales 0-1) by `.github/workflows/intelligence-deploy.yml`
on every push to `main` that touches `intelligence/`: tests, build and push
`ghcr.io/nmagera07/nhl-intelligence:<sha>`, update the app, then verify the
new revision is healthy and `GET /health` reports that commit.

Provider keys are Container App secrets, set once and never in CI or git:

```bash
az containerapp secret set -n nhl-intelligence -g nhl-dashboard-rg \
  --secrets gemini-api-key=<key> groq-api-key=<key>
```

`GET /health` shows the running commit and which providers are configured
(names only). The service previously ran on Google Cloud Run via Terraform;
that was retired in October 2026.
