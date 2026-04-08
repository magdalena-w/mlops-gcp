"""
Pipeline Runner

Compiles the KFP pipeline to JSON and submits it to Vertex AI.
Can be run locally or from GitHub Actions.

Usage:
    python pipelines/run.py \
        --data-bucket PROJECT-mlops-data \
        --model-bucket PROJECT-mlops-models \
        --pipeline-bucket PROJECT-mlops-pipeline-artifacts

    # Or with custom hyperparameters:
    python pipelines/run.py \
        --data-bucket PROJECT-mlops-data \
        --model-bucket PROJECT-mlops-models \
        --pipeline-bucket PROJECT-mlops-pipeline-artifacts \
        --n-estimators 200 \
        --max-depth 10 \
        --threshold 0.90
"""

import argparse
import os

from google.cloud import aiplatform
from kfp import compiler

from pipelines.pipeline import wine_training_pipeline


def compile_pipeline(output_path: str = "pipelines/compiled/pipeline.json") -> str:
    """Compile the pipeline to a JSON spec."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    compiler.Compiler().compile(
        pipeline_func=wine_training_pipeline,
        package_path=output_path,
    )
    print(f"Pipeline compiled to: {output_path}")
    return output_path


def run_pipeline(
    data_bucket: str,
    model_bucket: str,
    pipeline_bucket: str,
    n_estimators: int = 100,
    max_depth: int = 5,
    threshold: float = 0.85,
    compile_only: bool = False,
    enable_caching: bool = True,
):
    """Compile and submit the pipeline to Vertex AI."""

    # --- Compile ---
    template_path = compile_pipeline()

    if compile_only:
        print("Compile-only mode — skipping submission.")
        return

    # --- Resolve project and region from environment or gcloud ---
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.popen(
        "gcloud config get-value project 2>/dev/null"
    ).read().strip()
    region = os.environ.get("GOOGLE_CLOUD_REGION", "europe-central2")

    if not project:
        raise ValueError(
            "Set GOOGLE_CLOUD_PROJECT env var or run 'gcloud config set project PROJECT_ID'"
        )

    print(f"Project: {project}")
    print(f"Region:  {region}")

    # --- Submit to Vertex AI ---
    aiplatform.init(project=project, location=region)

    job = aiplatform.PipelineJob(
        display_name="wine-classifier-training",
        template_path=template_path,
        pipeline_root=f"gs://{pipeline_bucket}/runs",
        parameter_values={
            "data_bucket": data_bucket,
            "model_bucket": model_bucket,
            "data_path": "raw/wine_data.csv",
            "test_size": 0.2,
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "accuracy_threshold": threshold,
            "random_seed": 42,
        },
        enable_caching=enable_caching,
    )

    print("Submitting pipeline...")
    job.run(sync=False)  # Don't block — we can monitor in Console
    print(f"Pipeline submitted! Monitor at:")
    print(f"  https://console.cloud.google.com/vertex-ai/pipelines/runs?project={project}")


def main():
    parser = argparse.ArgumentParser(description="Compile and run the training pipeline")
    parser.add_argument("--data-bucket", required=True, help="GCS bucket with training data")
    parser.add_argument("--model-bucket", required=True, help="GCS bucket for model artifacts")
    parser.add_argument("--pipeline-bucket", required=True, help="GCS bucket for pipeline artifacts")
    parser.add_argument("--n-estimators", type=int, default=100, help="Number of trees")
    parser.add_argument("--max-depth", type=int, default=5, help="Max tree depth")
    parser.add_argument("--threshold", type=float, default=0.85, help="Min accuracy to register")
    parser.add_argument("--compile-only", action="store_true", help="Only compile, don't submit")
    parser.add_argument("--no-cache", action="store_true", help="Disable KFP step caching")
    args = parser.parse_args()

    run_pipeline(
        data_bucket=args.data_bucket,
        model_bucket=args.model_bucket,
        pipeline_bucket=args.pipeline_bucket,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        threshold=args.threshold,
        compile_only=args.compile_only,
        enable_caching=not args.no_cache,
    )


if __name__ == "__main__":
    main()