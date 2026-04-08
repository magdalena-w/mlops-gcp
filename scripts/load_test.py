"""
Load test for the Wine Classifier API.

Generates concurrent prediction requests with realistic Wine dataset
samples. Useful for:
  - Verifying the HPA scales up under load
  - Populating Grafana dashboards with real metrics
  - Benchmarking p50/p95/p99 latency

Usage:
    # Port-forward first:
    kubectl port-forward svc/wine-classifier 8080:80 -n serving

    # Then run the load test:
    python scripts/load_test.py --url http://localhost:8080 --duration 60 --rps 20
"""

import argparse
import json
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


# Sample Wine dataset rows (one per class) — used to generate realistic requests
WINE_SAMPLES = [
    # class 0 (high alcohol, high proline)
    [14.23, 1.71, 2.43, 15.6, 127.0, 2.8, 3.06, 0.28, 2.29, 5.64, 1.04, 3.92, 1065.0],
    [13.2,  1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.4, 1050.0],
    # class 1 (medium alcohol, low proline)
    [12.37, 0.94, 1.36, 10.6, 88.0, 1.98, 0.57, 0.28, 0.42, 1.95, 1.05, 1.82, 520.0],
    [12.33, 1.1, 2.28, 16.0, 101.0, 2.05, 1.09, 0.63, 0.41, 3.27, 1.25, 1.67, 680.0],
    # class 2 (low flavanoids, high color intensity)
    [12.86, 1.35, 2.32, 18.0, 122.0, 1.51, 1.25, 0.21, 0.94, 4.1, 0.76, 1.29, 630.0],
    [13.27, 4.28, 2.26, 20.0, 120.0, 1.59, 0.69, 0.43, 1.35, 10.2, 0.59, 1.56, 835.0],
]


@dataclass
class Result:
    latency_ms: float
    status: int
    error: str | None = None


def perturb(sample: list[float]) -> list[float]:
    """Add small random noise so requests aren't identical (better for metrics)."""
    return [v * random.uniform(0.95, 1.05) for v in sample]


def make_request(url: str) -> Result:
    payload = json.dumps({"data": perturb(random.choice(WINE_SAMPLES))}).encode()
    req = urllib.request.Request(
        f"{url}/predict",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
            latency = (time.perf_counter() - start) * 1000
            return Result(latency_ms=latency, status=resp.status)
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return Result(latency_ms=latency, status=0, error=str(e))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * p / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def run_load_test(url: str, duration: int, rps: int, workers: int):
    print(f"Load test: {url} for {duration}s at ~{rps} req/s ({workers} workers)")
    print("-" * 60)

    results: list[Result] = []
    interval = 1.0 / rps
    end_time = time.time() + duration

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        last_report = time.time()

        while time.time() < end_time:
            futures.append(executor.submit(make_request, url))
            time.sleep(interval)

            # Progress report every 5 seconds
            if time.time() - last_report >= 5:
                done_count = sum(1 for f in futures if f.done())
                print(f"  Sent: {len(futures):>5} | Completed: {done_count:>5}")
                last_report = time.time()

        # Drain remaining
        for future in as_completed(futures):
            results.append(future.result())

    # --- Summary ---
    print("-" * 60)
    successes = [r for r in results if r.status == 200]
    failures = [r for r in results if r.status != 200]
    latencies = [r.latency_ms for r in successes]

    print(f"Total requests:   {len(results)}")
    print(f"Successes:        {len(successes)} ({100 * len(successes) / len(results):.1f}%)")
    print(f"Failures:         {len(failures)}")

    if latencies:
        print(f"\nLatency (ms):")
        print(f"  min:  {min(latencies):.1f}")
        print(f"  p50:  {percentile(latencies, 50):.1f}")
        print(f"  p95:  {percentile(latencies, 95):.1f}")
        print(f"  p99:  {percentile(latencies, 99):.1f}")
        print(f"  max:  {max(latencies):.1f}")
        print(f"  mean: {sum(latencies) / len(latencies):.1f}")

    if failures:
        print(f"\nSample errors:")
        for f in failures[:3]:
            print(f"  {f.error}")


def main():
    parser = argparse.ArgumentParser(description="Load test the Wine Classifier API")
    parser.add_argument("--url", default="http://localhost:8080", help="Base URL")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--rps", type=int, default=20, help="Target requests per second")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent workers")
    args = parser.parse_args()

    run_load_test(args.url, args.duration, args.rps, args.workers)


if __name__ == "__main__":
    main()