# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

**Phase 0 complete. Phase 1 (Feast) is next.** The compose stack is built and healthy: Postgres, Redis,
MLflow, and three Airflow processes. The frozen holdout is carved, content-hashed, and sealed in a committed
manifest (`scripts/carve_holdout.py`, `holdout_manifest.json`), enforced by pytest. CI runs lint (Ruff) and
pytest on push and PR. The README and a cost note are written. Nothing above the infrastructure and holdout
layer exists yet: no feature repo, no training code, no server, no DAGs.

The authoritative spec is a build plan kept outside version control, along with `CLAUDE.local.md`. If work
needs a phase's definition of done or its scope table and the plan isn't available, ask rather than guess —
the invariants below are a summary of it, not a replacement.

### Local setup

`.env` is required and gitignored. Without it, Airflow's bind-mounted `dags/` and `logs/` end up owned by a
UID that doesn't exist on the host:

```bash
echo "AIRFLOW_UID=$(id -u)" > .env
```

## What this project is

A drift-triggered continuous-training platform, run entirely in `docker-compose` on one machine. A PyTorch
tabular fraud classifier is served by FastAPI; Evidently compares live prediction/feature windows against a
fixed reference window; the drift score is exported to Prometheus and charted in Grafana; when it crosses a
threshold an Airflow monitor DAG triggers a train DAG, which retrains, logs to MLflow, and moves the
`champion` alias to the challenger **only if it beats the incumbent on a frozen holdout**.

Project 4 of a four-repo portfolio (`rag-api`, `inference-gateway`, `retrain-pipeline`, `drift-sentinel`).
This one is the deliberate Python/PyTorch/data-engineering anchor; the other three are Go. The distinction
from `retrain-pipeline` matters and should stay visible in the README: that repo is code- and schedule-
triggered with a human governance gate; this one is **evidence-triggered with an automated metric gate**,
and adds the feature-store and live-monitoring stages the portfolio otherwise lacks.

## Architectural invariants

These are load-bearing. Changing any of them changes what the project demonstrates.

- **The frozen holdout is carved in Phase 0 and never changes.** It is a fixed early time slice, versioned by
  hash, and is the single ruler for every model version. Splitting at train time would make metrics
  incomparable across versions and defeat the promotion gate.
- **Promotion is gated on that holdout.** A challenger that loses to the incumbent champion is never promoted;
  the DAG holds and alerts. This is the safety property that lets retraining be automated at all.
- **The MLflow registry is the control plane.** The FastAPI server loads whatever version the `champion` alias
  points at — promotion changes serving behavior with no redeploy, no image build, no restart of the pipeline.
  Promotion is a single metadata write in Postgres; the artifact was already written when the run was logged.
  **Use aliases, not stages.** MLflow 3 deprecated the `Production`/`Staging` stages the build plan describes;
  the current mechanism is `models:/<name>@champion`. The legacy `current_stage` column still exists on
  `model_versions`, but aliases live in `registered_model_aliases` and are what this project writes.
- **The server enriches from Feast online, it does not trust the request.** The caller sends an *entity key*;
  the server fetches that entity's features from Redis. This is what proves offline/online parity and prevents
  training-serving skew.
- **Every prediction is logged with its features to Postgres.** The prediction log is the raw material the
  drift monitor consumes — without it there is nothing to compare against the reference window.
- **Drift is a Prometheus metric wired to a trigger, not a report.** The core thesis is "observability is a
  trigger, not a dashboard." An Evidently HTML report that a human must remember to open does not satisfy the
  definition of done.
- **No Kubernetes, no cloud cost in the MVP.** Every component is a `docker-compose` service. The tabular MLP
  trains on CPU in seconds. Cloud deploy is optional Phase 7, after the MVP is already on the resume.

## Data flow

Three paths, deliberately decoupled:

1. **Serving (always on):** client → FastAPI `/predict` → Feast online store (Redis) for features → model
   loaded from the MLflow registry via the `champion` alias → response; features + prediction written to
   Postgres; `/metrics` scraped by Prometheus.
2. **Monitoring (hourly, cheap):** Airflow monitor DAG → Evidently compares the current window of logged
   predictions against the frozen reference window → data drift and prediction drift computed *separately* →
   score exported to Prometheus → Grafana; threshold breach fires the trigger.
3. **Training (rare, expensive):** `TriggerDagRunOperator` → train DAG → Feast offline store for a
   point-in-time-correct training frame → PyTorch training with early stopping → MLflow logs params/metrics/
   model and registers a version → gate compares challenger to champion on the frozen holdout → promote or
   hold.

The monitor and trainer are **separate DAGs on purpose**: the monitor is cheap and frequent, training is
expensive and rare, and each stays single-purpose.

## Commands

These work today:

```bash
docker compose config --quiet   # validate the compose file; silent means valid
docker compose up -d            # bring up all six services
docker compose up -d --build    # ...rebuilding images first (needed after editing a Dockerfile)
docker compose ps               # status + health of each service
docker compose down             # stop; named volumes survive
docker compose down -v          # stop and DELETE volumes — wipes the registry and all runs

docker compose exec postgres psql -U drift -d drift     # MLflow's database
docker compose exec postgres psql -U drift -d airflow   # Airflow's database
```

MLflow UI on :5000, Airflow UI on :8080 (`admin`/`admin`).

Not yet real — fill in as each phase lands:

| Purpose | Command | Lands in |
|---|---|---|
| Lint + tests (CI runs these on PR) | `pytest` | Phase 0 |
| Register Feast entities and feature views | `feast apply` | Phase 1 |
| Push latest feature values into Redis | `feast materialize` | Phase 1 |
| Train, evaluate against the frozen holdout, log + register in MLflow | `python training/train.py` | Phase 2 |

## Compose stack notes

- **Airflow runs LocalExecutor with four services**, not the official file's nine — no Celery broker, no
  workers, no Flower, and the triggerer is skipped since nothing uses deferrable tasks. Adding any of them
  back needs a reason.
- **MLflow and Airflow share one Postgres server but separate databases** (`drift` and `airflow`). The
  `airflow` database is created by `docker/postgres-init.sql`, which the Postgres image runs **only when the
  data directory is empty** — so adding anything to that script requires `docker compose down -v` to take
  effect.
- **MLflow needs a custom image** (`docker/mlflow.Dockerfile`) because the official one ships without a
  Postgres driver.
- **`--serve-artifacts` is load-bearing**: the training script runs on the host, so artifacts must upload over
  HTTP rather than to a container path the host cannot see.
- Every service has a healthcheck, and every `depends_on` is gated on `service_healthy` or
  `service_completed_successfully` — never the bare short form.

## Metrics discipline

The dataset is heavily imbalanced fraud data, so **accuracy lies** — 99.8% on a 99.8/0.2 split is the
do-nothing baseline. Report precision, recall, F1, and PR-AUC in `metrics.json`, and gate promotion on one of
those, never accuracy.

Every MLflow run should carry enough to be reproducible six months later: full config as params, plus dataset
hash and git SHA as tags.

## Scope discipline

**Phase 5 is the MVP cut line** — when the closed loop runs end to end and the README GIF exists, the project
ships and goes on the resume. Explicitly parked, and not to be reintroduced without a reason: Kafka or any
streaming ingestion, Kubernetes, SHAP/feature-drift attribution, canary and shadow deploys, multi-GPU
training, multi-model serving, and cloud deploy (optional Phase 7, after the MVP is already on the resume).
If work drifts toward any of them, say so directly and ask whether it gets to a shippable result faster or
slower.

Resume claims stay factual until the system is instrumented and has produced real numbers.