"""
Model Evaluation & Registration Component

Evaluates the trained model on the held-out test set. If the model
meets the accuracy threshold, it registers the model and its baseline
to a versioned path in GCS. Otherwise, it logs the failure and skips
registration.

This is the quality gate of the pipeline — it prevents bad models
from reaching production.
"""

from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model, Metrics


@dsl.component(
    base_image="python:3.10-slim",
    packages_to_install=[
        "pandas==2.1.4",
        "scikit-learn==1.3.2",
        "joblib==1.3.2",
        "google-cloud-storage==2.14.0",
    ],
)
def evaluate_and_register(
    test_dataset: Input[Dataset],
    model_artifact: Input[Model],
    model_bucket: str,
    accuracy_threshold: float,
    eval_metrics: Output[Metrics],
) -> bool:
    """Evaluate model on test data and register to GCS if it passes."""
    import json
    import os
    from datetime import datetime, timezone
    import joblib
    import pandas as pd
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
    from google.cloud import storage

    # --- Load test data and model ---
    df = pd.read_csv(test_dataset.path)
    feature_columns = [c for c in df.columns if c != "target"]
    X_test = df[feature_columns]
    y_test = df["target"]

    model = joblib.load(model_artifact.path)

    # --- Evaluate ---
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average="macro")
    precision = precision_score(y_test, y_pred, average="macro")
    recall = recall_score(y_test, y_pred, average="macro")

    print(f"Test accuracy:  {accuracy:.4f}  (threshold: {accuracy_threshold})")
    print(f"Test F1 (macro): {f1:.4f}")
    print(f"Test precision:  {precision:.4f}")
    print(f"Test recall:     {recall:.4f}")

    # --- Log metrics (cast to Python types — numpy types break JSON) ---
    eval_metrics.log_metric("test_accuracy", float(round(accuracy, 4)))
    eval_metrics.log_metric("test_f1_macro", float(round(f1, 4)))
    eval_metrics.log_metric("test_precision_macro", float(round(precision, 4)))
    eval_metrics.log_metric("test_recall_macro", float(round(recall, 4)))
    eval_metrics.log_metric("accuracy_threshold", float(accuracy_threshold))

    # --- Quality gate ---
    passed = accuracy >= accuracy_threshold
    eval_metrics.log_metric("passed_threshold", int(passed))

    if not passed:
        print(f"FAILED: accuracy {accuracy:.4f} < threshold {accuracy_threshold}")
        print("Model NOT registered.")
        return False

    # --- Register model to GCS ---
    print("PASSED: Registering model to GCS...")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    version_path = f"wine-classifier/{timestamp}"

    client = storage.Client()
    bucket = client.bucket(model_bucket)

    # Upload model
    model_blob = bucket.blob(f"{version_path}/model.joblib")
    model_blob.upload_from_filename(model_artifact.path)

    # Upload baseline if it exists
    baseline_path = model_artifact.path.replace(".pkl", "") + "_baseline.json"
    if os.path.exists(baseline_path):
        baseline_blob = bucket.blob(f"{version_path}/baseline.json")
        baseline_blob.upload_from_filename(baseline_path)

    # Upload metadata
    metadata = {
        "version": timestamp,
        "test_accuracy": round(accuracy, 4),
        "test_f1_macro": round(f1, 4),
        "test_precision_macro": round(precision, 4),
        "test_recall_macro": round(recall, 4),
        "n_test_samples": len(X_test),
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "accuracy_threshold": accuracy_threshold,
    }
    metadata_blob = bucket.blob(f"{version_path}/metadata.json")
    metadata_blob.upload_from_string(json.dumps(metadata, indent=2))

    # Update "latest" pointer
    latest_blob = bucket.blob("wine-classifier/latest.json")
    latest_blob.upload_from_string(json.dumps({"version": timestamp}, indent=2))

    print(f"Registered: gs://{model_bucket}/{version_path}/")
    eval_metrics.log_metric("registered_version", timestamp)

    return True