"""
Wine Classifier Training Pipeline

Vertex AI Pipeline (KFP v2) with three steps:
  1. Ingest  — read from GCS, validate, split train/test
  2. Train   — fit RandomForest, save model + feature baseline
  3. Evaluate — test metrics, register to GCS if above threshold

The pipeline is parameterized so it can be triggered with different
data paths, hyperparameters, and thresholds without code changes.
"""

from kfp import dsl

from pipelines.ingest import ingest_data
from pipelines.train import train_model
from pipelines.evaluate import evaluate_and_register


@dsl.pipeline(
    name="wine-classifier-training",
    description="Train, evaluate, and conditionally register a Wine classifier",
)
def wine_training_pipeline(
    data_bucket: str,
    model_bucket: str,
    data_path: str = "raw/wine_data.csv",
    test_size: float = 0.2,
    n_estimators: int = 100,
    max_depth: int = 5,
    accuracy_threshold: float = 0.85,
    random_seed: int = 42,
):
    # Step 1: Ingest and split data
    ingest_task = ingest_data(
        data_bucket=data_bucket,
        data_path=data_path,
        test_size=test_size,
        random_seed=random_seed,
    )

    # Step 2: Train model on training split
    train_task = train_model(
        train_dataset=ingest_task.outputs["train_dataset"],
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_seed=random_seed,
    )

    # Step 3: Evaluate on test split and register if threshold met
    evaluate_and_register(
        test_dataset=ingest_task.outputs["test_dataset"],
        model_artifact=train_task.outputs["model_artifact"],
        model_bucket=model_bucket,
        accuracy_threshold=accuracy_threshold,
    )