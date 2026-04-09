# Model Evaluation Metrics

This document explains why model quality is evaluated with multiple metrics (not just accuracy), how each metric is computed, and how the pipeline's quality gate prevents bad models from reaching production.

## Why accuracy alone is a bad quality gate

Accuracy answers one question: *what fraction of predictions were correct?* That's useful, but it hides critical failure modes.

**The class-imbalance trap.** Imagine a fraud detection model on data where 99% of transactions are legitimate. A model that predicts "not fraud" for every transaction scores 99% accuracy — and catches zero fraud cases. Accuracy tells you nothing about whether the model is actually doing its job.

**The per-class trap.** A multi-class model can have 85% accuracy overall while being useless on one specific class. If the Wine classifier predicts class 0 perfectly, class 1 perfectly, but gets class 2 wrong 70% of the time, the overall number still looks acceptable — but anyone relying on class 2 predictions is getting garbage.

**The threshold trap.** Most classifiers return probabilities, and the decision threshold (usually 0.5) determines the label. Accuracy only reflects performance at that exact threshold — it says nothing about whether the model's probability ranking is reliable.

The pipeline's quality gate checks multiple metrics to close these gaps.

---

## The metrics

### Precision and recall

These are the two fundamental metrics for understanding classifier behavior. They're computed per class, then averaged.

**Precision** = `TP / (TP + FP)` — of all the times the model predicted class X, how often was it actually class X?

**Recall** = `TP / (TP + FN)` — of all actual class X samples, how many did the model catch?

The tradeoff between them is unavoidable: almost any change that improves precision hurts recall, and vice versa.

Which matters more depends on what the prediction triggers downstream:

- **High precision matters when false positives are costly.** A spam filter that incorrectly flags real emails frustrates users. A fraud detection model that flags legitimate transactions generates customer support calls. In these cases, be confident before you act.
- **High recall matters when false negatives are costly.** A cancer screening model that misses a real tumor is worse than one that flags a healthy patient for further review. A security system that misses an intruder is worse than one that sometimes alarms on the wind.

For the Wine classifier, neither side is obviously more costly — it's a demo dataset — so the quality gate uses recall as the "catch the minority classes" check.

### F1 score

F1 is the harmonic mean of precision and recall: `2 × (P × R) / (P + R)`.

The harmonic mean punishes imbalance. If precision is 1.0 and recall is 0.0, the arithmetic mean is 0.5 (sounds fine!) but F1 is 0 (correctly indicating the model is useless). This makes F1 a good "single number" summary when you want one value that reflects both precision and recall.

**Macro vs weighted vs micro averaging:**
- **Macro** — unweighted mean across classes. Treats every class equally regardless of sample count.
- **Weighted** — weighted by class support. Dominant classes drive the number.
- **Micro** — aggregate TP/FP/FN across all classes first, then compute. For single-label multi-class, this equals accuracy.

The pipeline logs both macro and weighted F1. Macro surfaces class-specific weakness; weighted reflects actual dataset distribution.

### ROC-AUC

The **ROC curve** plots true positive rate against false positive rate as you sweep the decision threshold from 0 to 1. Each point on the curve represents a different threshold.

**ROC-AUC** (area under the curve) captures this in a single number: how well does the model *rank* positives above negatives, regardless of where you set the threshold?

- **0.5** = random guessing
- **1.0** = perfect ranking (every positive scores higher than every negative)
- **> 0.9** = strong model
- **< 0.7** = weak model

ROC-AUC is valuable because it's threshold-independent. If business requirements later demand higher sensitivity ("during flu season we care more about catching cases than avoiding false alarms"), a model with good ROC-AUC will still rank correctly at a lower threshold. A model chosen purely on accuracy-at-0.5 might not.

**Multi-class ROC-AUC** uses the "one-vs-rest" strategy: compute AUC for each class against the others, then average. The pipeline uses macro-averaged OvR AUC.

**Caveat**: On severely imbalanced data, ROC-AUC can be misleadingly high because the ROC curve compresses into the corner. Precision-Recall AUC is a better choice there. The Wine dataset is balanced, so ROC-AUC works fine.

### Confusion matrix

A table of `actual class × predicted class` counts. It's not a single number — it's a diagnostic tool for understanding *which* classes the model confuses.

Example for a 3-class Wine model:

```
                Predicted
              0    1    2
Actual  0  [ 12    0    0  ]
        1  [  0   14    0  ]
        2  [  0    1    9  ]
```

Read across rows: of the 10 actual class 2 samples, 9 were correctly predicted as class 2, and 1 was misclassified as class 1. That tells you class 1 and class 2 are slightly confusable but class 0 is clearly separated from both.

The pipeline stores the confusion matrix in `metadata.json` alongside the model. When a quality gate fails, this is the first thing to inspect — it tells you *where* the model is failing, not just *that* it's failing.

---

## The multi-metric quality gate

The pipeline's `evaluate.py` component registers a model only if it passes **all three** of these gates:

| Gate | Threshold | What it prevents |
|------|-----------|------------------|
| **Accuracy** | ≥ 0.85 | Obviously broken models |
| **Per-class recall** | ≥ 0.70 on every class | "Good overall, terrible on one class" |
| **ROC-AUC** | ≥ 0.90 | Models that only work at the default 0.5 threshold |

Each gate is logged independently as a Vertex AI pipeline metric (`gate_accuracy_passed`, `gate_min_per_class_recall_passed`, `gate_roc_auc_passed`), so when a model is rejected, you can see exactly which check failed.

**Why these thresholds:**
- **0.85 accuracy** — high enough to rule out obviously bad models, low enough to be achievable on this dataset
- **0.70 per-class recall** — below this means the model misses more than 30% of a given class, which is too weak for anything real
- **0.90 ROC-AUC** — a reasonable bar for "strong ranking" on balanced multi-class data

These are tunable via constants in `evaluate.py`. In a real project, the thresholds would be negotiated with stakeholders based on what the model is used for.

---

## Reading the metadata.json

Every registered model has a `metadata.json` in GCS with the full metric breakdown:

```json
{
  "version": "20260409-120000",
  "registered_at": "2026-04-09T12:00:00+00:00",
  "n_test_samples": 36,
  "metrics": {
    "accuracy": 0.9722,
    "f1_macro": 0.9721,
    "f1_weighted": 0.9723,
    "precision_macro": 0.9762,
    "recall_macro": 0.9691,
    "roc_auc_ovr": 0.9981,
    "per_class": {
      "0": {"precision": 1.0, "recall": 1.0, "f1": 1.0},
      "1": {"precision": 0.9286, "recall": 1.0, "f1": 0.963},
      "2": {"precision": 1.0, "recall": 0.9074, "f1": 0.9515}
    }
  },
  "confusion_matrix": [[12, 0, 0], [0, 14, 0], [0, 1, 9]],
  "quality_gates": {
    "accuracy_threshold": 0.85,
    "min_per_class_recall": 0.70,
    "min_roc_auc": 0.90,
    "all_passed": true
  }
}
```

Fetch the metadata for the current model:

```bash
VERSION=$(gcloud storage cat gs://YOUR_PROJECT-mlops-models/wine-classifier/latest.json | jq -r .version)
gcloud storage cat gs://YOUR_PROJECT-mlops-models/wine-classifier/$VERSION/metadata.json
```

---

## Deliberately not measured

**Calibration** — whether a "90% confident" prediction is actually correct 90% of the time. Important for models whose probabilities are used directly (e.g., expected-value calculations). Skipped here for simplicity, but worth adding for probability-sensitive applications.

**Fairness metrics** — differential precision/recall across demographic groups. Critical for any model making decisions about people. Not applicable to the Wine dataset but essential in finance, healthcare, hiring, etc.

**Inference latency at the pipeline level** — this is a serving concern tracked in [SLO.md](./SLO.md) via the `prediction_latency_seconds` histogram, not a model quality concern.

**Training vs validation loss curves** — these matter for tuning and debugging but aren't part of the pass/fail decision.

---

## The general principle

Metrics are there to surface specific failure modes. Every metric you add corresponds to a failure you'd rather catch at pipeline time than in production. The goal isn't to log as many metrics as possible — it's to have enough coverage that the quality gate catches the failures that would actually matter downstream.