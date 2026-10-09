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

**AI engineering**
- Rebuilt an LLM chat feature to run on free providers (Gemini → Groq) with
  automatic failover, cutting AI cost to $0 after the paid key ran out;
  evaluated models against ground-truth questions (hosted 5/5 vs. local 7B 3/5).
- Cut LLM context from ~1.3M characters (98% silently truncated) to ~3.4K
  measured tokens of purpose-built summaries, so answers became correct and
  free tiers became viable.

**Security**
- Removed a write-capable database credential that was exposed as a plain-text
  environment variable on the API, enforcing least privilege (the API only
  holds a read-only credential, stored as a secret).

**Data and modeling**
- Rebuilt a Monte Carlo playoff-odds model (regressed team ratings, game
  model calibrated on ~4,000 real games, official tiebreakers) and validated
  it by backtesting against 3 past seasons: 15% lower Brier score overall,
  29% lower in early season.
- Added expected-goals (xG) data to the model and proved the gain with
  leave-one-season-out backtesting on as-of data (no lookahead): a further
  3.7% lower Brier overall and 7.6% early in the season.

**Data and backend**
- Fixed a data-integrity bug where cut and released players stayed on team
  rosters indefinitely (~580 stale records), using a soft-delete flag that
  preserves player history.
- Rebuilt the live game box score by merging three NHL API endpoints in
  parallel, with graceful degradation when the optional feeds fail.

---

## 2026-10-09 — Adjusted xG: a clean null result

**Question:** MoneyPuck also publishes *adjusted* xG (corrected for score
effects and home ice, and/or for rebound "flurries"). Would a cleaner version
of xG make the playoff odds better?

**What I did:** Added an `--xg-measures` option to the backtest so all four xG
flavors run side by side through the same grid and leave-one-season-out test.

**Result:** No. Score/venue-adjusted xG tied raw xG (Brier 0.1161 vs 0.1162,
well inside the noise, and the same held-out score). Flurry adjustment was
slightly *worse* (0.1167), so rebound chances seem to carry real signal about
team strength. I didn't change production.

**What I learned:**
- Score effects mostly average out over a season, and the 50/50 blend with real
  goals already smooths the noise the adjustment targets.
- Two "don't ship" results in a row (strength of schedule, then this) say the
  model has gotten what it can from team-level season totals. The next gains
  need *new information* (goaltending, roster changes), not a polished version
  of the same numbers.
- Making experiments cheap to run is what makes null results cheap to accept.

**Interview angle:** "Tell me about an experiment that didn't work." I tested
it properly, it didn't beat what was live, so I kept the simpler model.

---

## 2026-10-09 — Playoff odds v2.1: the right new data beats more tuning

**What happened:** The diagnostics said tuning was maxed out and the
remaining error came from information the model didn't have. So I added
MoneyPuck's expected goals (xG), which measures the *quality* of chances
rather than whether they happened to go in.

**What I learned:**
- **No lookahead in backtests.** MoneyPuck's season files are full-season
  totals, and using them to "predict" November would leak the future. Their
  game-by-game file let me compute xG *as of* each checkpoint date, which is
  the only honest way to test it.
- **This one passed the bar strength of schedule failed:** 3.7% better
  overall, 7.6% better on Nov 1, better on held-out seasons, and the *same
  recipe* won in every leave-one-out fold (50% goals + 50% xG, last season's
  xG as the prior). Consistent winners are real; shifting winners are noise.
- **It helps exactly where theory says:** early in the season, when goals
  are noisy. By March, a team's actual goals have caught up with its chance
  quality, so xG adds nothing.
- **Design for the dependency failing:** if MoneyPuck is down, the
  simulator falls back to the goals-only model instead of failing the job.
- **Read the data license:** MoneyPuck is free for non-commercial use *with
  credit*, so the credit is in the UI (with a test so it can't disappear),
  and the downloader identifies itself honestly instead of posing as a browser.

---

## 2026-10-09 — Playoff odds v3: when the right answer is "don't change it"

**What happened:** Set out to improve the playoff model further *without* new
data. Built better diagnostics first: a calibration table, leave-one-season-out
testing, a wider tuning grid over 4 seasons, and a strength-of-schedule
variant. The finding: **the model was already about as good as this data
allows, so I didn't ship a "v3."**

**What I learned:**
- **Calibration:** bucket predictions and check reality. When v2 says 75%,
  about 75% of those teams make it; v1's "85%" teams made it only 71% of the
  time. A model can have a decent overall score and still be systematically
  overconfident, and calibration shows that.
- **Leave-one-season-out exposes overfitting.** Settings tuned on three
  seasons scored *worse* on the fourth (0.1244) than the existing fixed
  settings (0.1208). All the top settings were within 0.0005 of each other,
  which is noise. Past that point, more tuning just fits randomness.
- **Negative results are results.** Strength-of-schedule ratings are sound in
  theory, but measured about 0.3% better (noise) and no better under honest
  testing. So it's documented as an experiment, not shipped. Shipping it would
  have added complexity for nothing.
- **Know which lever is left.** With goals-only data the model is at its
  ceiling. Remaining error comes from information it doesn't have (shot
  quality, goaltending), so the next real gain needs new data (MoneyPuck xG),
  not more tuning.

**Interview angle:** "Tell me about a time you decided *not* to ship
something." Measured it honestly, found no real gain, kept it simple.

---

## 2026-10-09 — NHL Intelligence: free AI, real evaluation, less magic

**What happened:** The AI chat was broken: its paid OpenAI key ran out. I
didn't want to pay for an API, so we rebuilt it to run on free tiers, moved it
into this repo, and deployed it to Azure next to the API.

**What I learned:**
- **Check what you're actually sending.** The chat sent the model the raw
  JSON, cut off at 24,000 characters. For league questions that kept **2%**
  of the data: half the standings, no leaders, no playoff odds. So the model
  *couldn't* answer correctly. The fix was a compact, purpose-built summary
  per page, not a bigger model.
- **Measure tokens, don't estimate.** I guessed ~3,700 tokens with the
  "4 characters per token" rule. The real count was **5,752**, because JSON
  full of numbers packs tighter. That was over the local model's 4,096-token
  window, which *silently* drops the start of the prompt, instructions included.
- **Do the reasoning in code, give the model the conclusion.** Small models
  couldn't work out wild-card spots from two rank columns. Computing a plain
  `playoff_spot` ("Eastern wild card 2 (in)") made those answers correct.
  Cheap, deterministic code beats asking an LLM to do math.
- **Evaluate with ground truth.** Five questions with known answers, run
  against each model:

  | | Gemini Flash-Lite | Groq gpt-oss-20b | Local Qwen 7B |
  |---|---|---|---|
  | Correct | **5/5** | **5/5** | 3/5 |

  A 1B model confidently named the wrong overtime scorer even with the right
  answer in front of it. Model size matters for *reliability*, not just fluency.
- **Design for free-tier limits:** every free tier has caps, so the service
  tries providers in order and falls over to the next on a rate limit or
  outage. Keys have no payment method attached, so the worst case is "busy,"
  never a bill. Streaming can only switch providers *before* the first word.
- **Separate service, same repo:** the chat is its own deployable service
  (its own keys, limits, and failure mode), but lives in the dashboard repo
  because the two change together. Repos follow ownership; services follow
  failure boundaries.
- **Small verification bugs hide in "success" states:** the first deploy
  went red because Azure said `RunningAtMaxScale`, not `Running`. Production
  was fine; the check was too strict. The backend workflow had the same
  latent bug.

**Interview angle:** "How do you make an LLM feature reliable and cheap?"
Shrink and structure the context, compute anything deterministic in code,
evaluate against known answers, and design for provider failure.

---

## 2026-10-08 — Playoff odds v2: making a model better, and proving it

**What happened:** The playoff odds were overconfident early in the season.
After a few games, teams showed 0% or 99%. The model rated teams by their
current point %, and four games is mostly luck. I rebuilt it with an AI
pair-programmer. My part was spotting that the numbers looked wrong,
deciding what "better" meant, and insisting we *measure* it before shipping.

**The concepts, in plain English:**
- **Monte Carlo simulation:** instead of a formula for playoff chances, play
  the rest of the season 10,000 times with weighted dice and count how often
  each team gets in.
- **Regression to the mean:** a coin that lands heads 4 times in a row isn't
  a magic coin. Early on, the model leans on last season and lets this
  season take over as games pile up (blended as "45 pseudo-games").
- **Uncertainty:** we don't *know* how good a team is in October, so each
  simulated season varies every team's strength a little. That's what keeps
  October odds humble instead of 0% / 99%.
- **Calibration:** instead of guessing things like home-ice advantage, we
  measured them from ~4,000 real games: home teams win 54.5% of the time
  between equal teams, 22% of games go to OT, and 32% of those go to a
  shootout.
- **Backtesting:** pretend it's November 1st of a past season, run the model,
  and check it against who actually made the playoffs. Repeat across dates
  and seasons to get a score.
- **Brier score:** "how far off were the probabilities." Lower is better, and
  saying 50% for everyone scores 0.25. The old model scored **0.252** on
  Nov 1, worse than not trying. The new one scored **0.178**.

**Results:** overall Brier 0.152 → 0.129 (15% better); early November 29% better.

**The 30-second interview version:**
> "My dashboard shows playoff odds by simulating the rest of the season
> 10,000 times. Early in the season they were wildly overconfident, because
> a 4-0 team looked like a lock. I rebuilt the model to blend this season's
> results with last season's, so it starts cautious and gets more confident
> as games pile up. To prove it was better, I backtested both versions
> against three past seasons: 15% more accurate overall, and 29% more
> accurate in early November, when the old model was worse than guessing 50/50."

**Follow-up questions to expect:**
- *"Why not use an existing model?"* Building it taught me how they work, and
  I made it measurable so I can keep improving it instead of guessing.
- *"How do you know it's not overfit?"* The game-level numbers were fit on
  the same seasons I tested on, so the absolute score is a bit optimistic.
  The fair comparison is old vs. new under the same conditions, and that gap
  was big. (Admitting a model's limits unprompted is a good look.)
- *"What would you do next?"* Add shot-quality data (expected goals), and
  re-run the calibration script each offseason.

**For front-end interviews,** lead with the product side, not the math:
noticing that 0%/100% in October looked wrong to a user, showing "<1%"
instead of a misleading "0%", hiding stale odds instead of showing last
season's, and measuring before shipping.

**Be honest about AI help.** Don't claim I derived the math. The real skills
were judgment (this looks wrong), framing (what does "better" mean?), and
verification (prove it with a backtest).

---

## 2026-10-08 — A frozen standings day, and my first hotfix

**What happened:** Standings were missing a game for 6 teams. A manual test run
of the daily job at 8:56pm ET wrote that day's snapshot mid-games, and the
script used `ON CONFLICT DO NOTHING`, so the scheduled 2am run's final numbers
were silently skipped. The first run of the day won.

**What I learned:**
- For "one row per day" data, decide **which write should win**. Here it's the
  latest (`DO UPDATE`), so an early or partial run can't freeze the day.
- **Hotfix workflow:** the fix was urgent, but `dev` had an unfinished redesign
  on it. So: branch from `main`, cherry-pick just the fix, PR, merge, deploy,
  then merge `main` back into `dev` so the branches don't drift.
- Manual "test" runs against production data aren't free. That one caused the bug.

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
- **Root cause:** the pipeline still existed (under an Azure DevOps org that
  the Azure Portal doesn't show; it's listed at aex.dev.azure.com/me), but its
  last run was July 18. It never *failed*. GitHub stopped notifying it of new
  commits. It wasn't using the Azure Pipelines GitHub App (no checks ever
  appeared on commits), and by October the repo had zero webhooks, so the
  push webhook or the OAuth connection behind it was most likely removed or
  expired. No runs means no failures, which means no alerts.
- Azure DevOps and the Azure Portal are effectively separate products
  (DevOps grew out of VSTS/TFS). DevOps orgs aren't Azure resources and don't
  show up in a subscription, which is part of why this was easy to forget.
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
- **Rotation is where mistakes happen.** On the first try, the job's secret got
  the `< >` placeholder brackets from a command template, and my local `.env`
  ended up with the owner URL pasted into both `DATABASE_URL` and
  `API_DATABASE_URL`. What helped:
  - Commands that **read the value from a file** (`dotenv_values(".env")`)
    instead of having me paste it, so I never retype a password.
  - **Verify right after a change** (a test job run, a `SELECT current_user`
    per connection string) instead of finding out at the next scheduled run.
  - The heartbeat monitor emailed about the failed run on its own, which is
    exactly what it's for.

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
