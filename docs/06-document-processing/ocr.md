# Optical Character Recognition (OCR) Engine

## Level 1: Conceptual Overview

The OCR engine extracts character text sequences and character bounding boxes from document page images when native text layers are missing, corrupted, or formatted as scanned bitmaps.

---

## Level 2: Implementation Details

### Engine Architecture

Implemented in [deepdoc/vision/ocr.py](file:///home/logan78/Desktop/ragflow/deepdoc/vision/ocr.py#L25) and C++/ONNX bindings.

```mermaid
flowchart LR
    PageImage[Page Image BGR] --> TextDet[Text Detector / DBNet ONNX]
    TextDet --> CroppedBoxes[Cropped Character Line Images]
    CroppedBoxes --> TextRec[Text Recognizer / CRNN CTC Model]
    TextRec --> Spans[Extracted Text Spans & Confidence Scores]
```

### Remote DLA & OCR Services

For high-concurrency production deployments, DeepDoc supports offloading OCR and DLA to remote microservices via environment variables:
- `DEEPDOC_URL` or `TENSORRT_DLA_SVR`
- Service Endpoints: [deepdoc/server/endpoints/ocr_endpoint.py](file:///home/logan78/Desktop/ragflow/deepdoc/server/endpoints/ocr_endpoint.py#L15), [dla_endpoint.py](file:///home/logan78/Desktop/ragflow/deepdoc/server/endpoints/dla_endpoint.py#L15)
