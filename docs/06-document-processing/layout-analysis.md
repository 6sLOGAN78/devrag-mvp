# Document Layout Analysis (DLA)

## Level 1: Conceptual Overview

Document Layout Analysis (DLA) is the core computer vision component in DeepDoc. It processes document page images and predicts bounding box regions labeled with structural semantic categories: Title, Text, Figure, Figure Caption, Table, Table Caption, Header, Footer, Reference, and Equation.

---

## Level 2: Implementation Details

### Model Architecture & Labels

Implemented in [deepdoc/vision/layout_recognizer.py](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py#L33):

Labels defined in `LayoutRecognizer.labels`:
```python
labels = [
    "_background_",
    "Text",
    "Title",
    "Figure",
    "Figure caption",
    "Table",
    "Table caption",
    "Header",
    "Footer",
    "Reference",
    "Equation",
]
```

### Mathematical Formulas

#### 1. Overlap Ratio Formula
To match native PDF text character boxes $B_{\text{text}}$ with predicted visual layout regions $B_{\text{layout}}$:

$$\text{Overlap\_Ratio}(B_{\text{text}}, B_{\text{layout}}) = \frac{\text{Area}(B_{\text{text}} \cap B_{\text{layout}})}{\text{Area}(B_{\text{text}})}$$

In `findLayout()` ([deepdoc/vision/layout_recognizer.py](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py#L115)):
A text box is assigned to a layout region if $\text{Overlap\_Ratio} \ge 0.4$.

#### 2. Intersection over Union (IoU) Formula
Used in Non-Maximum Suppression (`nms` operator in `deepdoc/vision/operators.py`) to eliminate duplicate layout boxes:

$$\text{IoU}(B_1, B_2) = \frac{\text{Area}(B_1 \cap B_2)}{\text{Area}(B_1 \cup B_2)} = \frac{\text{Area}(B_1 \cap B_2)}{\text{Area}(B_1) + \text{Area}(B_2) - \text{Area}(B_1 \cap B_2)}$$

#### 3. Vertical Y-Axis Sort Criterion
Layout elements are sorted top-to-bottom using line-height thresholding in [deepdoc/vision/layout_recognizer.py](file:///home/logan78/Desktop/ragflow/deepdoc/vision/layout_recognizer.py#L99):

$$\text{Threshold}_y = \frac{1}{2 \cdot N} \sum_{i=1}^{N} (y_{i,\text{bottom}} - y_{i,\text{top}})$$
