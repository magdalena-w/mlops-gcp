# Service Level Objectives

This document defines SLIs, SLOs, and error budgets for the Wine Classifier model serving system.

**SLI** (Service Level Indicator) — a quantitative measure of service health, expressed as the ratio of good events to total events.
**SLO** (Service Level Objective) — the target value for an SLI over a time window.
**Error budget** — `1 - SLO`, the amount of unreliability you can "spend" without violating the contract.

## Scope

These SLOs apply to the user-facing model serving endpoint (`/predict` on the `wine-classifier` service in the `serving` namespace). Training pipeline reliability is tracked separately — pipelines are batch workloads, not user-facing.

---

## SLI 1 — Availability

**What it measures**: The proportion of `/predict` requests that return a successful response (HTTP 2xx).

**Why it matters**: Users care that the service responds at all. Availability failures include crashed pods, model loading failures, and unhandled exceptions.

### Definition

```promql
sum(rate(predictions_total[5m]))
/
(sum(rate(predictions_total[5m])) + sum(rate(prediction_errors_total[5m])))
```

- **Good events**: `predictions_total` — successful predictions across all classes
- **Total events**: successes + errors of any type (`model_not_loaded`, `invalid_input`, `internal`)

### SLO target

**99.5% availability over a rolling 30-day window.**

This allows for approximately:
- 3.6 hours of total downtime per month
- 50.4 minutes per week

### Error budget policy

If the monthly budget is consumed, freeze non-critical deployments until the incident is resolved and a postmortem is written.

---

## SLI 2 — Latency

**What it measures**: The proportion of `/predict` requests served within 100ms.

**Why it matters**: Prediction latency directly affects downstream user experience. A slow prediction is effectively a failed one if it exceeds the caller's timeout.

### Definition

```promql
sum(rate(prediction_latency_seconds_bucket{le="0.1"}[5m]))
/
sum(rate(prediction_latency_seconds_count[5m]))
```

- **Good events**: requests with latency ≤ 100ms (from the histogram bucket)
- **Total events**: all latency observations

### SLO target

**95% of requests complete in under 100ms over a rolling 30-day window.**

This threshold is calibrated to actual load test results (p95 ~76ms under moderate load, spiking to ~180ms during HPA scale-up events). A stricter target would force tighter HPA tuning or larger minimum replica counts.

### Error budget policy

Latency budget violations trigger capacity reviews — either the HPA needs tuning or baseline replica count needs to increase.

---

## SLI 3 — Model Quality (Feature Drift)

**What it measures**: The proportion of input features whose distribution matches the training baseline within an acceptable tolerance.

**Why it matters**: This is the ML-specific SLI that distinguishes an MLOps system from a generic web service. A model serving successfully fast doesn't mean it's serving *correctly* — drifted inputs silently degrade prediction quality without any HTTP error.

### Definition

```promql
count(feature_drift_zscore < 2)
/
count(feature_drift_zscore)
```

- **Good events**: features with z-score below 2 (within ~2 standard deviations of the training mean)
- **Total events**: all 13 monitored features

The underlying metric (`feature_drift_zscore`) is computed every 15 minutes by the drift detector CronJob, which compares the 5-minute rolling average of each feature from live traffic against the baseline captured during training.

### SLO target

**100% of features within tolerance at all times during any 1-hour rolling window.**

This is a stricter-than-usual SLO because drift is binary in practice: if a feature drifts, the model's predictions are suspect until retraining happens. Unlike latency, drift doesn't have graceful degradation.

### Error budget policy

Drift SLO violations trigger automatic retraining via the GitHub Actions `retrain.yml` workflow. If retraining doesn't resolve the drift (e.g., real-world distribution has shifted permanently), the feature baseline needs to be updated and the SLO reset.

---

## Burn rate alerting

Rather than alerting on raw threshold violations, we alert on *error budget burn rate* — the speed at which the budget is being consumed. This follows the SRE workbook multi-window approach.

For the **latency** SLO (95% target, 5% error budget):

### Fast burn alert

Fires when the current burn rate would exhaust the entire 30-day budget in 1 hour. Threshold: **14.4× normal rate**.

```promql
(
  1 - (
    sum(rate(prediction_latency_seconds_bucket{le="0.1"}[1h]))
    /
    sum(rate(prediction_latency_seconds_count[1h]))
  )
) > (14.4 * 0.05)
```

### Slow burn alert

Fires when the current burn rate would exhaust the budget in 3 days. Threshold: **6× normal rate**.

```promql
(
  1 - (
    sum(rate(prediction_latency_seconds_bucket{le="0.1"}[6h]))
    /
    sum(rate(prediction_latency_seconds_count[6h]))
  )
) > (6 * 0.05)
```

**Why two windows**: A fast burn catches acute outages (page immediately). A slow burn catches chronic degradation that would otherwise accumulate undetected until the budget runs out.

For the **availability** SLO (99.5% target, 0.5% error budget), the same math applies with `0.005` instead of `0.05`.

---

## Summary

| SLI | SLO Target | Window | Fast burn threshold |
|-----|-----------|--------|---------------------|
| Availability | 99.5% success rate | 30 days | 14.4× (1h burn) |
| Latency | 95% under 100ms | 30 days | 14.4× (1h burn) |
| Model quality | 100% features within tolerance | 1 hour | Binary — any drift violates |

## What these SLIs deliberately don't measure

- **Prediction accuracy** — impossible to measure in real time without labels. Approximated via drift detection.
- **Throughput** — not an SLI. Throughput is a capacity planning concern, not a reliability one.
- **Training pipeline success rate** — training is a batch workload, not user-facing. Tracked as a separate operational metric.
- **Cost per prediction** — a business metric, not a reliability SLI. Worth tracking separately.

## References

- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [The Four Golden Signals](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals)