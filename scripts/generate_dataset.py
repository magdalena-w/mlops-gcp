"""
Generate the Wine dataset for the MLOps pipeline.

Creates a CSV file from scikit-learn's Wine dataset with:
- 178 samples, 13 features, 3 classes
- Feature names cleaned for pipeline compatibility
"""

import logging
from pathlib import Path

import pandas as pd
from sklearn.datasets import load_wine

logger = logging.getLogger(__name__)


def generate_dataset(output_dir: str | Path = None) -> dict:
    """
    Generate and save the Wine dataset.
    
    Args:
        output_dir: Directory to save the CSV. Defaults to 'data/' relative to script.
    
    Returns:
        Dictionary with dataset metadata.
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "data"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "wine_data.csv"
    
    try:
        wine = load_wine(as_frame=True)
        df = pd.concat([wine.data, wine.target.rename("target")], axis=1)
        
        # Clean column names for pipeline compatibility
        df.columns = [col.replace("/", "_").replace(" ", "_").lower() for col in df.columns]
        
        df.to_csv(output_file, index=False, encoding="utf-8")
        
        metadata = {
            "path": str(output_file),
            "n_samples": len(df),
            "n_features": len(df.columns) - 1,
            "n_classes": df["target"].nunique(),
            "class_distribution": df["target"].value_counts().to_dict(),
        }
        
        logger.info(f"Dataset saved to {output_file}")
        logger.info(f"  Samples: {metadata['n_samples']}, Features: {metadata['n_features']}, Classes: {metadata['n_classes']}")
        
        return metadata
    
    except Exception as e:
        logger.error(f"Failed to generate dataset: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_dataset()