"""
Model Training Component

Trains a RandomForestClassifier on the Wine dataset, logs training
metrics, and saves both the model and a feature baseline (mean/std
of training features) for drift detection later.
"""

from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model, Metrics


@dsl.component(
    base_image="python:3.10-slim",
    packages_to_install=["pandas==2.1.4", "scikit-learn==1.3.2", "joblib==1.3.2"],
)
def train_model(
    train_dataset: Input[Dataset],
    model_artifact: Output[Model],
    train_metrics: Output[Metrics],
    n_estimators: int,
    max_depth: int,
    random_seed: int,
):
    """Train a RandomForest classifier and output the model artifact."""
    import json
    import os
    import joblib
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, f1_score, classification_report

    # --- Load training data ---
    df = pd.read_csv(train_dataset.path)
    feature_columns = [c for c in df.columns if c != "target"]
    X = df[feature_columns]
    y = df["target"]

    print(f"Training on {len(X)} samples, {len(feature_columns)} features")

    # --- Train ---
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_seed,
        n_jobs=-1,
    )
    model.fit(X, y)

    # --- Evaluate on training data ---
    y_pred = model.predict(X)
    accuracy = accuracy_score(y, y_pred)
    f1 = f1_score(y, y_pred, average="macro")

    print(f"Train accuracy: {accuracy:.4f}")
    print(f"Train F1 (macro): {f1:.4f}")
    print(classification_report(y, y_pred))

    # --- Log metrics (cast to Python types — numpy types break JSON) ---
    train_metrics.log_metric("train_accuracy", float(round(accuracy, 4)))
    train_metrics.log_metric("train_f1_macro", float(round(f1, 4)))
    train_metrics.log_metric("n_estimators", int(n_estimators))
    train_metrics.log_metric("max_depth", int(max_depth))
    train_metrics.log_metric("n_samples", int(len(X)))
    train_metrics.log_metric("n_features", int(len(feature_columns)))

    # Log feature importances (top 5)
    importances = dict(zip(feature_columns, model.feature_importances_))
    for feat, imp in sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]:
        train_metrics.log_metric(f"importance_{feat}", float(round(imp, 4)))

    # --- Save model ---
    os.makedirs(os.path.dirname(model_artifact.path), exist_ok=True)
    joblib.dump(model, model_artifact.path)

    # --- Save feature baseline for drift detection ---
    # Stored alongside the model so serving can compare incoming data
    baseline = {
        "feature_columns": feature_columns,
        "means": X.mean().to_dict(),
        "stds": X.std().to_dict(),
        "mins": X.min().to_dict(),
        "maxs": X.max().to_dict(),
    }
    baseline_path = model_artifact.path.replace(".pkl", "") + "_baseline.json"
    with open(baseline_path, "w") as f:
        json.dump(baseline, f, indent=2)

    print(f"Model saved to: {model_artifact.path}")
    print(f"Baseline saved to: {baseline_path}")