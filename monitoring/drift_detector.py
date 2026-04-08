"""
Feature Drift Detector

Runs as a Kubernetes CronJob. For each feature:
  1. Reads the training baseline (mean, std) from GCS
  2. Queries Prometheus for the current feature mean over the last hour
  3. Computes a normalized drift score (absolute z-score of the shift)
  4. Pushes the score back to Prometheus via Pushgateway

This is a simplified drift metric — a production version would use
full histogram comparison (PSI — Population Stability Index) with
bucketed distributions. For this project the normalized z-score is
good enough to demonstrate the concept and trigger alerts.

Output metric:
  feature_drift_zscore{feature_name="alcohol"} 0.12
  feature_drift_zscore{feature_name="proline"} 2.34  <- drifting!
"""

import json
import logging
import os
import sys
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


PROMETHEUS_URL = os.environ["PROMETHEUS_URL"]
PUSHGATEWAY_URL = os.environ["PUSHGATEWAY_URL"]
BASELINE_PATH = os.environ.get("BASELINE_PATH", "/baseline/baseline.json")
JOB_NAME = "feature_drift"


def load_baseline(path: str) -> dict:
    """Load the training baseline (means, stds, etc.) from local file."""
    if not os.path.exists(path):
        logger.error(f"Baseline file not found: {path}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def query_prometheus(query: str) -> float | None:
    """Execute an instant PromQL query and return a single scalar."""
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.error(f"Prometheus query failed: {e}")
        return None

    if data.get("status") != "success":
        logger.error(f"Prometheus query error: {data}")
        return None

    results = data.get("data", {}).get("result", [])
    if not results:
        return None

    try:
        return float(results[0]["value"][1])
    except (KeyError, ValueError, IndexError):
        return None


def compute_drift_scores(baseline: dict) -> dict[str, float]:
    """For each feature, compute |live_mean - baseline_mean| / baseline_std."""
    baseline_means = baseline["means"]
    baseline_stds = baseline["stds"]

    scores = {}

    for feature_name in baseline_means:
        # PromQL: compute the running average of the feature value
        # over the last 5 minutes from the histogram _sum and _count series.
        query = (
            f'sum(rate(input_feature_value_sum{{feature_name="{feature_name}"}}[5m])) '
            f'/ sum(rate(input_feature_value_count{{feature_name="{feature_name}"}}[5m]))'
        )

        live_mean = query_prometheus(query)
        if live_mean is None:
            logger.info(f"  {feature_name}: no live data (skipping)")
            continue

        baseline_mean = baseline_means[feature_name]
        baseline_std = baseline_stds[feature_name]

        if baseline_std == 0:
            drift = 0.0
        else:
            drift = abs(live_mean - baseline_mean) / baseline_std

        scores[feature_name] = drift
        flag = " ⚠ DRIFT" if drift > 2.0 else ""
        logger.info(
            f"  {feature_name}: baseline={baseline_mean:.3f}, "
            f"live={live_mean:.3f}, z-score={drift:.3f}{flag}"
        )

    return scores


def push_metrics(scores: dict[str, float]) -> None:
    """Push drift scores to Prometheus Pushgateway."""
    if not scores:
        logger.warning("No drift scores to push")
        return

    # Pushgateway expects one metric family per POST.
    # We format all labels into the metric line.
    lines = ["# TYPE feature_drift_zscore gauge"]
    for feature_name, score in scores.items():
        lines.append(f'feature_drift_zscore{{feature_name="{feature_name}"}} {score}')

    body = "\n".join(lines) + "\n"
    url = f"{PUSHGATEWAY_URL}/metrics/job/{JOB_NAME}"

    req = urllib.request.Request(
        url,
        data=body.encode(),
        headers={"Content-Type": "text/plain"},
        method="PUT",  # PUT replaces all metrics for this job
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info(f"Pushed {len(scores)} metrics to Pushgateway ({resp.status})")
    except Exception as e:
        logger.error(f"Pushgateway push failed: {e}")
        sys.exit(1)


def main():
    logger.info(f"Loading baseline from {BASELINE_PATH}")
    baseline = load_baseline(BASELINE_PATH)
    logger.info(f"Baseline has {len(baseline['means'])} features")

    logger.info("Computing drift scores...")
    scores = compute_drift_scores(baseline)

    logger.info("Pushing metrics to Pushgateway...")
    push_metrics(scores)

    logger.info("Done.")


if __name__ == "__main__":
    main()