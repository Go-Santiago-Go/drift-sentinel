# ADR 0001: Evidence-triggered continuous training on docker-compose

## Context

This is the fourth project in a portfolio I am building to demonstrate MLOps and AI-infrastructure
skills. My other three repos are Go services. This one is the deliberate Python and machine-learning
anchor, and it needs to demonstrate something the others do not: a model that retrains itself in
response to evidence, with an automated safety gate, plus the feature-store and live-monitoring stages
a serving project alone would not show.

One of my sibling repos, `retrain-pipeline`, already covers scheduled retraining with a human approval
step. Repeating that would add no signal. The capability I find more interesting, and see less often,
is a loop that decides on its own when a model has gone stale and whether a fresh one is actually
better, with no person in the loop for the routine case.

Two constraints frame the build. Cost has to stay near zero, because I run this on one developer
machine and it exists to be finished and demoed, not operated. And it has to ship fast enough to go on
my resume, so scope needs a hard cut line.

## Decision

I am building a drift-triggered continuous-training platform that runs entirely in `docker-compose` on
one machine. The properties I chose to make load-bearing:

- **Evidence-triggered, not schedule-triggered.** A drift score computed from live prediction windows,
  not a cron timer, decides when to retrain. I wire observability to a trigger, not just a dashboard.
- **Automated metric gate on a frozen holdout.** I promote a retrained challenger only if it beats the
  incumbent champion on a fixed early holdout that never changes. A challenger that loses is held and
  alerts. This gate is the safety property that makes me comfortable automating retraining at all.
- **The MLflow registry is the control plane.** Serving loads whatever version the `champion` alias
  points at, so promotion changes behavior with a single metadata write, no redeploy or restart.
- **The server enriches from the online feature store, it does not trust the request.** The caller
  sends an entity key; the server fetches that entity's features from Redis. This proves offline and
  online parity and prevents training-serving skew.
- **No Kubernetes and no cloud cost in the MVP.** Every component is a compose service, and the tabular
  model trains on CPU in seconds. Cloud deploy is an optional later phase, after the MVP is on my
  resume.

## Consequences

Positive:

- I can demonstrate the whole drift to retrain to promote loop on one machine at zero cost, which
  keeps the project finishable.
- The automated gate on a frozen holdout gives me a concrete, defensible safety story for interviews.
- Using registry aliases as the control plane lets me show serving and training decoupled through
  metadata, a real MLOps pattern rather than a toy.

Negative:

- Single-node compose is not a production-scale deployment. I am leaving horizontal scale, high
  availability, and real streaming ingestion out of the MVP on purpose.
- Running everything locally means I defer some operational concerns (secrets management, cloud
  networking, autoscaling) rather than demonstrating them.

## Alternatives considered

- **Schedule-triggered retraining with a human gate:** I rejected this because it is exactly what
  `retrain-pipeline` already demonstrates. This project earns its place by being evidence-triggered
  with an automated gate.
- **Managed cloud services (SageMaker, managed vector and feature stores):** I rejected these for the
  MVP. They add cost and console setup without changing what the project proves, and they hide the
  mechanisms behind provider abstractions. Local-first keeps the moving parts legible.
- **Kubernetes:** I rejected it as overkill for a single-node CPU workload. It would add operational
  surface that competes with shipping and orchestration this project does not need.
