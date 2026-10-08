# NHL Intelligence

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

Set `OPENAI_API_KEY` in `.env`. It is used only by this service and must never be sent to the browser.

## Deploy to Google Cloud Run

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
