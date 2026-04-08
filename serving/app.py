"""
Wine Classifier — Model Serving API

Production-ready FastAPI server with:
- /predict   — inference with class probabilities
- /health    — liveness + readiness (model loaded check)
- /metrics   — Prometheus exposition format

Metrics exposed for monitoring:
- prediction_latency_seconds  — histogram with percentile buckets
- predictions_total           — counter per predicted class
- input_feature_value         — histogram per feature (for drift detection)

Model is loaded from a local path (mounted via init container or
downloaded at startup from GCS).
"""

import json
import logging
import os
import time

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
MODEL_PATH = os.getenv("MODEL_PATH", "/models/model.joblib")
BASELINE_PATH = os.getenv("BASELINE_PATH", "/models/baseline.json")
PORT = int(os.getenv("PORT", "8080"))

# Wine dataset feature names (in order)
FEATURE_NAMES = [
    "alcohol", "malic_acid", "ash", "alcalinity_of_ash", "magnesium",
    "total_phenols", "flavanoids", "nonflavanoid_phenols",
    "proanthocyanins", "color_intensity", "hue",
    "od280_od315_of_diluted_wines", "proline",
]

CLASS_NAMES = ["class_0", "class_1", "class_2"]

# --- Prometheus Metrics ---
PREDICTION_LATENCY = Histogram(
    "prediction_latency_seconds",
    "Time spent processing a prediction request",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

PREDICTIONS_TOTAL = Counter(
    "predictions_total",
    "Total number of predictions",
    ["class_label"],
)

INPUT_FEATURE = Histogram(
    "input_feature_value",
    "Distribution of input feature values (for drift detection)",
    ["feature_name"],
    buckets=[
        0, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
        12, 14, 16, 20, 50, 100, 200, 500, 1000, 2000,
    ],
)

MODEL_LOADED = Gauge(
    "model_loaded",
    "Whether the model is currently loaded (1=yes, 0=no)",
)

# --- Request/Response schemas ---
class PredictRequest(BaseModel):
    """Input features for prediction.

    Accepts either a flat dict of feature names → values,
    or a raw list of 13 floats in the standard Wine dataset order.
    """
    features: dict[str, float] | None = None
    data: list[float] | None = None

class PredictResponse(BaseModel):
    prediction: int
    class_name: str
    probabilities: dict[str, float]
    latency_ms: float

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_path: str

# --- App ---
app = FastAPI(
    title="Wine Classifier API",
    description="MLOps serving endpoint with Prometheus metrics",
    version="1.0.0",
)

model = None
baseline = None


@app.on_event("startup")
async def load_model():
    """Load model and baseline at startup."""
    global model, baseline

    # Load model
    if os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
        MODEL_LOADED.set(1)
        logger.info(f"Model loaded from {MODEL_PATH}")
    else:
        MODEL_LOADED.set(0)
        logger.warning(f"Model not found at {MODEL_PATH} — server will start but /predict will fail")

    # Load baseline (optional — drift detection still works without it)
    if os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH) as f:
            baseline = json.load(f)
        logger.info(f"Feature baseline loaded from {BASELINE_PATH}")
    else:
        logger.info("No baseline found — drift comparison unavailable")


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check for Kubernetes liveness and readiness probes."""
    return HealthResponse(
        status="healthy" if model is not None else "degraded",
        model_loaded=model is not None,
        model_path=MODEL_PATH,
    )


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """Run inference on input features."""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    start = time.perf_counter()

    # Parse input — accept either named features or raw array
    if request.features:
        try:
            X = np.array([[request.features[name] for name in FEATURE_NAMES]])
        except KeyError as e:
            raise HTTPException(status_code=422, detail=f"Missing feature: {e}")
    elif request.data:
        if len(request.data) != len(FEATURE_NAMES):
            raise HTTPException(
                status_code=422,
                detail=f"Expected {len(FEATURE_NAMES)} features, got {len(request.data)}",
            )
        X = np.array([request.data])
    else:
        raise HTTPException(status_code=422, detail="Provide 'features' dict or 'data' array")

    # Track input feature distributions (for drift detection via Prometheus)
    for i, name in enumerate(FEATURE_NAMES):
        INPUT_FEATURE.labels(feature_name=name).observe(float(X[0][i]))

    # Predict
    prediction = int(model.predict(X)[0])
    probabilities = model.predict_proba(X)[0]

    # Track prediction counts per class
    PREDICTIONS_TOTAL.labels(class_label=CLASS_NAMES[prediction]).inc()

    latency = time.perf_counter() - start
    PREDICTION_LATENCY.observe(latency)

    return PredictResponse(
        prediction=prediction,
        class_name=CLASS_NAMES[prediction],
        probabilities={CLASS_NAMES[i]: round(float(p), 4) for i, p in enumerate(probabilities)},
        latency_ms=round(latency * 1000, 2),
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(generate_latest(), media_type="text/plain; version=0.0.4")
