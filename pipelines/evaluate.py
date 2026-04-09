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
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from google.cloud import storage

    # --- Load test data and model ---
    df = pd.read_csv(test_dataset.path)
    feature_columns = [c for c in df.columns if c != "target"]
    X_test = df[feature_columns]
    y_test = df["target"]

    model = joblib.load(model_artifact.path)

    # --- Evaluate ---
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)  # Needed for ROC-AUC

    # Overall (macro-averaged) metrics
    accuracy = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    precision_macro = precision_score(y_test, y_pred, average="macro")
    recall_macro = recall_score(y_test, y_pred, average="macro")

    # Weighted average — reflects actual class distribution
    f1_weighted = f1_score(y_test, y_pred, average="weighted")

    # Per-class metrics — reveals class-specific failures
    precision_per_class = precision_score(y_test, y_pred, average=None)
    recall_per_class = recall_score(y_test, y_pred, average=None)
    f1_per_class = f1_score(y_test, y_pred, average=None)

    # ROC-AUC — threshold-independent ranking quality.
    # For multi-class: one-vs-rest, averaged.
    try:
        roc_auc = roc_auc_score(y_test, y_proba, multi_class="ovr", average="macro")
    except ValueError:
        # Happens if test set is missing a class
        roc_auc = 0.0

    # Confusion matrix — shows which classes the model confuses
    cm = confusion_matrix(y_test, y_pred)

    print(f"Test accuracy:       {accuracy:.4f}  (threshold: {accuracy_threshold})")
    print(f"Test F1 (macro):     {f1_macro:.4f}")
    print(f"Test F1 (weighted):  {f1_weighted:.4f}")
    print(f"Test precision:      {precision_macro:.4f}")
    print(f"Test recall:         {recall_macro:.4f}")
    print(f"Test ROC-AUC (OvR):  {roc_auc:.4f}")
    print()
    print("Per-class breakdown:")
    for cls in range(len(precision_per_class)):
        print(
            f"  class {cls}: precision={precision_per_class[cls]:.3f}, "
            f"recall={recall_per_class[cls]:.3f}, f1={f1_per_class[cls]:.3f}"
        )
    print()
    print("Confusion matrix:")
    print(cm)

    # --- Log metrics (cast to Python types — numpy types break JSON) ---
    eval_metrics.log_metric("test_accuracy", float(round(accuracy, 4)))
    eval_metrics.log_metric("test_f1_macro", float(round(f1_macro, 4)))
    eval_metrics.log_metric("test_f1_weighted", float(round(f1_weighted, 4)))
    eval_metrics.log_metric("test_precision_macro", float(round(precision_macro, 4)))
    eval_metrics.log_metric("test_recall_macro", float(round(recall_macro, 4)))
    eval_metrics.log_metric("test_roc_auc_ovr", float(round(roc_auc, 4)))
    eval_metrics.log_metric("accuracy_threshold", float(accuracy_threshold))

    # Per-class metrics — critical for spotting class-specific failures
    for cls in range(len(precision_per_class)):
        eval_metrics.log_metric(f"test_precision_class_{cls}", float(round(precision_per_class[cls], 4)))
        eval_metrics.log_metric(f"test_recall_class_{cls}", float(round(recall_per_class[cls], 4)))
        eval_metrics.log_metric(f"test_f1_class_{cls}", float(round(f1_per_class[cls], 4)))

    # --- Quality gate (multi-metric, not just accuracy) ---
    # A model is only registered if it passes ALL checks. This prevents
    # cases like "85% accuracy but 20% recall on class 2" from shipping.
    MIN_PER_CLASS_RECALL = 0.70
    MIN_ROC_AUC = 0.90

    gates = {
        "accuracy": accuracy >= accuracy_threshold,
        "min_per_class_recall": all(r >= MIN_PER_CLASS_RECALL for r in recall_per_class),
        "roc_auc": roc_auc >= MIN_ROC_AUC,
    }
    passed = all(gates.values())

    for gate_name, gate_passed in gates.items():
        eval_metrics.log_metric(f"gate_{gate_name}_passed", int(gate_passed))
    eval_metrics.log_metric("passed_threshold", int(passed))

    if not passed:
        print()
        print("FAILED quality gates:")
        for gate_name, gate_passed in gates.items():
            status = "PASS" if gate_passed else "FAIL"
            print(f"  {status}: {gate_name}")
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
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "n_test_samples": int(len(X_test)),
        "metrics": {
            "accuracy": round(accuracy, 4),
            "f1_macro": round(f1_macro, 4),
            "f1_weighted": round(f1_weighted, 4),
            "precision_macro": round(precision_macro, 4),
            "recall_macro": round(recall_macro, 4),
            "roc_auc_ovr": round(roc_auc, 4),
            "per_class": {
                str(cls): {
                    "precision": round(float(precision_per_class[cls]), 4),
                    "recall": round(float(recall_per_class[cls]), 4),
                    "f1": round(float(f1_per_class[cls]), 4),
                }
                for cls in range(len(precision_per_class))
            },
        },
        "confusion_matrix": cm.tolist(),
        "quality_gates": {
            "accuracy_threshold": accuracy_threshold,
            "min_per_class_recall": MIN_PER_CLASS_RECALL,
            "min_roc_auc": MIN_ROC_AUC,
            "all_passed": passed,
        },
    }
    metadata_blob = bucket.blob(f"{version_path}/metadata.json")
    metadata_blob.upload_from_string(json.dumps(metadata, indent=2))

    # Update "latest" pointer
    latest_blob = bucket.blob("wine-classifier/latest.json")
    latest_blob.upload_from_string(json.dumps({"version": timestamp}, indent=2))

    print(f"Registered: gs://{model_bucket}/{version_path}/")
    eval_metrics.log_metric("registered_version", timestamp)

    return True