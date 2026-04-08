"""
Download the latest registered model from GCS.

Used in two contexts:
  1. Kubernetes init container — pulls model before serving container starts
  2. Local development — download model to test serving locally

Usage:
    python download_model.py --bucket YOUR_PROJECT-mlops-models --dest /models
"""

import argparse
import json
import os
import sys

from google.cloud import storage


def download_latest_model(bucket_name: str, dest_dir: str) -> str:
    """Download the latest model version from GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # Read the latest version pointer
    latest_blob = bucket.blob("wine-classifier/latest.json")
    if not latest_blob.exists():
        print("ERROR: No latest.json found — has the pipeline run successfully?")
        sys.exit(1)

    latest = json.loads(latest_blob.download_as_text())
    version = latest["version"]
    version_path = f"wine-classifier/{version}"

    print(f"Latest model version: {version}")

    # Download model and baseline
    os.makedirs(dest_dir, exist_ok=True)

    files_to_download = ["model.joblib", "baseline.json", "metadata.json"]
    for filename in files_to_download:
        blob = bucket.blob(f"{version_path}/{filename}")
        dest_file = os.path.join(dest_dir, filename)
        if blob.exists():
            blob.download_to_filename(dest_file)
            print(f"  Downloaded: {filename}")
        else:
            print(f"  Skipped (not found): {filename}")

    # Print model metadata
    metadata_path = os.path.join(dest_dir, "metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            metadata = json.load(f)
        print(f"  Test accuracy: {metadata.get('test_accuracy')}")
        print(f"  Registered at: {metadata.get('registered_at')}")

    return version


def main():
    parser = argparse.ArgumentParser(description="Download latest model from GCS")
    parser.add_argument("--bucket", required=True, help="GCS models bucket name")
    parser.add_argument("--dest", default="/models", help="Local destination directory")
    args = parser.parse_args()

    download_latest_model(args.bucket, args.dest)


if __name__ == "__main__":
    main()