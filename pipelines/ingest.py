"""
Data Ingestion Component

Reads raw Wine dataset from GCS, validates schema, splits into
train/test sets, and outputs both as pipeline artifacts.

This is a KFP v2 lightweight component — dependencies are installed
at runtime, no custom container needed.
"""

from kfp import dsl
from kfp.dsl import Output, Dataset, Metrics


@dsl.component(
    base_image="python:3.10-slim",
    packages_to_install=["pandas==2.1.4", "scikit-learn==1.3.2", "gcsfs==2024.2.0"],
)
def ingest_data(
    data_bucket: str,
    data_path: str,
    test_size: float,
    random_seed: int,
    train_dataset: Output[Dataset],
    test_dataset: Output[Dataset],
    ingest_metrics: Output[Metrics],
):
    """Read data from GCS, validate, and split into train/test."""
    import pandas as pd
    from sklearn.model_selection import train_test_split

    # --- Read from GCS ---
    gcs_uri = f"gs://{data_bucket}/{data_path}"
    print(f"Reading data from: {gcs_uri}")
    df = pd.read_csv(gcs_uri)

    # --- Validate schema ---
    expected_columns = [
        "alcohol", "malic_acid", "ash", "alcalinity_of_ash", "magnesium",
        "total_phenols", "flavanoids", "nonflavanoid_phenols",
        "proanthocyanins", "color_intensity", "hue",
        "od280_od315_of_diluted_wines", "proline", "target",
    ]
    missing = set(expected_columns) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # --- Check for nulls ---
    null_counts = df.isnull().sum().sum()
    if null_counts > 0:
        print(f"WARNING: {null_counts} null values found, dropping rows")
        df = df.dropna()

    # --- Split ---
    train_df, test_df = train_test_split(
        df, test_size=test_size, random_state=random_seed, stratify=df["target"]
    )

    # --- Save outputs ---
    train_df.to_csv(train_dataset.path, index=False)
    test_df.to_csv(test_dataset.path, index=False)

    # --- Log metrics (cast to Python int — numpy int64 breaks JSON) ---
    ingest_metrics.log_metric("total_samples", int(len(df)))
    ingest_metrics.log_metric("train_samples", int(len(train_df)))
    ingest_metrics.log_metric("test_samples", int(len(test_df)))
    ingest_metrics.log_metric("num_features", int(len(df.columns) - 1))
    ingest_metrics.log_metric("null_values_found", int(null_counts))

    for cls in sorted(df["target"].unique()):
        ingest_metrics.log_metric(f"class_{int(cls)}_count", int((df["target"] == cls).sum()))

    print(f"Train: {len(train_df)} samples, Test: {len(test_df)} samples")