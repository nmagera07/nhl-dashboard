# NHL Intelligence

> Moved here from `atelier-ai-labs/nhl-intelligence` in October 2026; its
> commit history came along via `git subtree`. Part of the NHL Dashboard
> repo so API and chat changes ship together.

A standalone, grounded conversational layer for the NHL Dashboard. It reads structured data from the dashboard public API, so it never receives dashboard database credentials.

## How it answers

An **agent loop** (`app/main.py: run_agent`). The model gets the page's
context (player, team, game box score, or a small league summary) and a set of
**tools** (`app/tools.py`). Each round it either answers or asks for tools,
which run here, in parallel, and go back to it as results. At most 3 tool
rounds per question.

| Tool | For questions like |
|---|---|
| `get_standings` | "Who's in the wild-card race?" |
| `get_team` | "How's Florida doing?" |
| `get_playoff_odds` | "How have PIT's odds moved this season?" |
| `get_schedule` | "Who does Toronto play next week?" |
| `rank_schedule_strength` | "Who has the easiest remaining schedule?" |
| `simulate_scenario` | "What if PIT wins their next 4?" |
| `playoff_path` | "What does Detroit need over its next 10?" |
| `get_recent_results` | "How have the Penguins played lately?" |
| `get_game` | "How did PIT do last night? Who scored?" (latest game, a date, or vs. an opponent) |
| `find_player` / `get_leaders` | "How's Crosby doing?" / "Who leads in goals?" |

The model decides *what to ask*; the numbers come from the dashboard API and
the playoff-odds model's simulations (`GET /season-sim/scenario` and
`/season-sim/path` on the backend), never from the model's own arithmetic.

Budget notes: tool results are compact, and the league page sends a ~150-token
summary instead of full standings, since every round resends the conversation
and Groq's free tier caps tokens per minute. Gemini requires each tool call's
"thought signature" (`extra_content`) to be echoed back, so tool calls are
returned to the model exactly as received.

The chat streams a status line per tool ("Simulating 2,000 seasons…"), then
the answer with evidence labels for the data and tools used.

## Evals

`evals/` scores the agent on real questions, against real providers:

```bash
.venv/bin/python -m evals.run                                  # 12 cases, gemini + groq (~8 min)
.venv/bin/python -m evals.run --providers groq --cases scenario,pdo_reading
```

Each case's correct answer is computed live from the dashboard API, and the answer is
checked for the right **tool** (and arguments), the right **facts**/**number**, that it's
**grounded** (no percentage without a source in the tool results), and, for fuzzy
rubrics, by a **judge** (a different hosted provider, never a local model). Results
print as a scorecard and are saved to `evals/results/`. It uses real free-tier requests,
so it runs on demand (after prompt, tool, or model changes), not in CI; the scoring rules
themselves are unit-tested in `tests/test_eval_checks.py`.

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
