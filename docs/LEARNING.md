# Learning Log

What I've learned building this project: what happened, why it matters,
and how I'd describe it on a resume or in an interview. Newest first.

---

## Resume bullets

Ready-to-use lines, grouped by theme. Details for each are in the entries below.

**CI/CD and reliability**
- Migrated backend CI/CD from Azure DevOps to GitHub Actions with OIDC
  federated identity, removing every stored cloud credential from the pipeline.
- Added post-deploy verification (the new revision must be healthy *and* report
  the exact commit just deployed) plus a daily deploy-drift check, after finding
  production had silently run three-month-old code.
- Introduced a `dev` → `main` promotion workflow with branch protection and
  required frontend and backend test checks on every PR.

**Cloud and cost**
- Moved container images from Azure Container Registry to GitHub Container
  Registry with a zero-downtime expand → migrate → contract migration,
  cutting monthly hosting costs by ~87%.
- Consolidated daily data ingestion into a single scheduled Azure Container
  Apps Job with failure isolation between steps and automatic retry.

- Replaced a log-based Azure alert with a heartbeat monitor (healthchecks.io)
  that also detects a scheduled job that never runs, and cut the monthly
  Azure bill from ~$11.44 to ~$0.97.

**Security**
- Removed a write-capable database credential that was exposed as a plain-text
  environment variable on the API, enforcing least privilege (the API only
  holds a read-only credential, stored as a secret).

**Data and backend**
- Fixed a data-integrity bug where cut and released players stayed on team
  rosters indefinitely (~580 stale records), using a soft-delete flag that
  preserves player history.
- Rebuilt the live game box score by merging three NHL API endpoints in
  parallel, with graceful degradation when the optional feeds fail.

---

## 2026-10-08 — Heartbeat monitoring for the daily job

**What happened:** Swapped the Azure "ingestion is stale" alert for a
healthchecks.io heartbeat. The job pings `/start` when it begins, the plain URL
when it succeeds, and `/fail` when it fails.

**What I learned:**
- **Push vs. pull monitoring:** the old alert *looked* for a problem in the
  logs. A heartbeat expects a check-in and alerts when one **doesn't arrive**,
  so it catches the job never running at all. That's the same blind spot as
  the deploy that never ran.
- Monitoring calls should be **best-effort**: if healthchecks.io is down, the
  job still finishes. A ping failure is logged, never raised.
- Treat the ping URL as a secret (stored as a Container Apps secret), since
  anyone holding it could send fake "all good" pings.

---

## 2026-10-08 — Production was silently running July's code

**What happened:** After merging a PR, the frontend deploy finished and I
assumed everything had shipped. It hadn't. The backend's Azure DevOps pipeline
had stopped triggering after July 18, so production was running a three-month-old
backend, and the live scoreboard and game pages returned 404s in production the
whole time. I'd been testing locally, where the new code worked fine.

**Why no alert fired:** I *did* have Azure Monitor alerts: one for crashes and
one for stale ingestion. But they watch the **running app**, and the old app
was perfectly healthy. Nothing watched for "the code on `main` never got
deployed." A stale deploy looks healthy.

**What I learned:**
- Monitoring has layers. "Is the app healthy?" and "is the app running the
  right code?" are different questions, and I only had the first one covered.
- "The deploy finished" isn't the same as "the deploy worked." The new workflow
  only passes if production's `/health` reports the **exact commit** that was
  just deployed.
- A deploy can't report that it never ran. That takes a separate check, so a
  daily GitHub Action compares production's commit to `main` and fails if
  they've drifted.
- Root cause, as best I can tell: by October the Azure DevOps organization
  and pipeline no longer existed under my account at all. The pipeline didn't
  fail, it just vanished, which is the hardest kind of failure to notice.
- Watch out for silent schedules: GitHub disables scheduled workflows in public
  repos after 60 days without activity.

**Interview angle:** "Tell me about a production incident." This is a good one:
the detection gap, the root cause, and the fix in three layers (deploy status,
version reporting, drift detection).

---

## 2026-10-08 — Moving CI/CD from Azure DevOps to GitHub Actions (OIDC)

**What happened:** Replaced the broken Azure DevOps pipeline with a GitHub
Actions workflow: test → build → deploy → verify.

**What I learned:**
- **OIDC federated identity:** instead of storing an Azure password in GitHub,
  Azure is configured to trust tokens that GitHub issues for *one specific repo
  and environment* (`repo:nmagera07/nhl-dashboard:environment:production`).
  There's no secret to leak or expire, and expiring credentials are a common
  way pipelines quietly die.
- **Least privilege:** the deploy identity only gets Contributor on one resource
  group, not the whole subscription.
- **One place for everything:** frontend deploy, tests, Dependabot, and now the
  backend deploy all live in GitHub, so a failure is a red ❌ on the commit
  instead of something hidden in a separate tool.
- In single-revision mode, Azure Container Apps keeps the *old* revision serving
  traffic while a new one starts. Checking the public URL right after a deploy
  can return 200 from the old version, so the verify step checks the new
  revision's own health too.

---

## 2026-10-08 — Cutting the Azure bill ~87% (ACR → GHCR)

**What happened:** Pulled actual costs from the Azure Cost Management API.
September was $11.44, and **$10 of it was Azure Container Registry**: just
storing Docker images. Everything else fit in free tiers.

**What I learned:**
- Look at the real bill before guessing. Cost Management showed exactly which
  service cost what.
- **GitHub Container Registry** is free for public images. The repo is already
  public and the image contains no secrets (credentials are injected at runtime),
  so a public image is fine. Azure pulls it anonymously, so there's no
  registry password to manage either.
- **Expand → migrate → contract:** first publish to both registries while still
  deploying from the old one (expand), confirm Azure can pull from the new one,
  switch deploys (migrate), then delete the old registry (contract).
  Production never depended on something that hadn't been verified.
- **Audit what you're actually running.** Cleaning up turned up a *second*,
  empty registry left over from the initial setup (setup tools like
  `az containerapp up` can create resources with random names). It had been
  billing every month with zero images in it. Listing everything in the
  resource group (`az resource list -g ...`) is worth doing now and then.

---

## 2026-10-08 — A plain-text database credential on the API

**What happened:** While cleaning up, I found the API container had the
**write-capable** `DATABASE_URL` set as a plain-text environment variable. The
API never even used it, since it connects with a separate read-only credential.

**What I learned:**
- **Least privilege:** the API should only hold the credential it needs (read-only).
  The ingestion job is the only thing that should be able to write.
- **Secrets vs. env vars:** plain env vars are visible to anyone with read access
  to the resource. Credentials belong in the platform's secret store.
- After a credential has been exposed, **rotate it** too. Removing it isn't enough.

---

## 2026-10-06 — Rosters full of players who'd been cut

**What happened:** Toronto showed 50 players instead of 23. The ingestion
upserted every player on a team's current roster but never removed anyone who'd
left, so training-camp cuts and released players stayed on their old team forever.

**What I learned:**
- An "upsert-only" sync drifts over time. You also have to handle records that
  *disappear* from the source.
- **Soft delete** (`on_roster = false`) instead of deleting rows: player pages,
  career stats, and the leaderboard still need those players.
- Guard against bad upstream data: if the API returns an empty roster, skip
  the cleanup instead of wiping the whole team.
- Database migrations should be **backward compatible**: adding a column with a
  default first means the old code keeps working until the new code deploys.

---

## 2026-10-07 — Box score: reading the API docs (and the actual responses)

**What happened:** The game page looked broken because it asked the NHL's
`/boxscore` endpoint for data it doesn't have. The scoring summary and team
stats live in `/landing` and `/right-rail`.

**What I learned:**
- Inspect real API responses instead of assuming a shape.
- Fetch independent endpoints **in parallel** (about 0.1s for all three).
- **Graceful degradation:** the core endpoint is required, the extras are
  optional, so one feed being down doesn't blank the whole page.

---

## 2026-10-07 — Polling vs. websockets vs. SSE

**Question I asked:** "Is the live score using websockets?"

**Answer:** No, it's **polling**: the page refetches every 30s while a game is
live. React only re-renders what changed, so it *looks* live.

**What I learned:**
- Polling fits here: the NHL API is plain REST (it can't push), traffic is low,
  and stateless requests are easy to scale and cache.
- If many users watched the same game, the better design is for the server to
  poll the NHL once and push to clients with **Server-Sent Events** (one-way,
  simpler than websockets).
- The live endpoints don't touch the database at all, but they do hit the NHL
  API once per viewer. A short server-side cache would make 500 viewers cost
  the same as 1.

**Interview angle:** "When would you use websockets?" Now I have a concrete
answer from my own app.

---

## 2026-10-03 — Treating it like a production app

**What happened:** Set up a `dev` branch for testing locally, with PRs into
`main` (which auto-deploys), branch protection, and required test checks.

**What I learned:**
- Use **merge commits** (not squash) between long-lived branches like
  `dev` → `main`, or the branches drift apart and PRs get messy.
- Grouped Dependabot updates (one weekly PR per ecosystem, targeting `dev`)
  beat a dozen single-package PRs piling up.
- Major dependency bumps can carry hidden requirements: jsdom 30 and vitest 5
  needed Node 22, so CI on Node 20 broke even though tests passed locally.
