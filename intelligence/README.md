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

## Deploy to Google Cloud Run

> Being replaced: this service is moving to Azure Container Apps next to the
> dashboard API, deployed by GitHub Actions. The Terraform below still
> describes the current (OpenAI-based) Cloud Run deployment.

Deployment uses a container image plus Terraform. Terraform owns the Google
APIs, Artifact Registry repository, runtime service account, Secret Manager
secret, Cloud Run service, and public invoker policy. The OpenAI key value is
added separately so it never enters Terraform state.

Prerequisites: authenticated `gcloud`, Terraform 1.5+, Docker or Cloud Build,
and a Google Cloud project with billing enabled.

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit project_id and the image path in terraform.tfvars.

terraform init

# Bootstrap APIs, the image repository, service account, and empty secret.
terraform apply \
  -target='google_project_service.required' \
  -target='google_artifact_registry_repository.images' \
  -target='google_service_account.runtime' \
  -target='google_secret_manager_secret.openai_api_key'

# Add the key outside Terraform. The command reads it without echoing it.
read -s OPENAI_KEY
printf '%s' "$OPENAI_KEY" | gcloud secrets versions add \
  nhl-intelligence-openai-api-key --data-file=- --project=YOUR_PROJECT_ID
unset OPENAI_KEY

# From the repository root, build an immutable image tag.
cd ../..
IMAGE="us-east4-docker.pkg.dev/YOUR_PROJECT_ID/nhl-intelligence-images/nhl-intelligence:$(git rev-parse --short HEAD)"
gcloud builds submit --tag "$IMAGE" --project=YOUR_PROJECT_ID .

# Put the exact IMAGE value in infra/terraform/terraform.tfvars, then deploy.
cd infra/terraform
terraform apply
terraform output -raw service_url
```

Use the final output as `VITE_NHL_INTELLIGENCE_URL` in the dashboard build.
