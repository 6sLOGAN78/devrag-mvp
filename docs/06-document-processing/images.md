# Images Processing Subsystem

## Level 1: Conceptual Overview

The Images Processing subsystem extracts, crops, captions, and embeds visual elements (photos, diagrams, flowcharts, infographics, plots) found in documents.

---

## Level 2: Implementation Details

### VLM Captioning & Image Deduplication

Implemented in [rag/app/picture.py](file:///home/logan78/Desktop/ragflow/rag/app/picture.py#L20) and `rag/utils/base64_image.py`.

1. **Image Hashing**: Generates unique visual image ID using `image2id()` in [rag/utils/base64_image.py](file:///home/logan78/Desktop/ragflow/rag/utils/base64_image.py#L15).
2. **VLM Integration**: Sends image binary stream to Vision Language Models (`GptV4` in `rag/llm/cv_model.py`) to generate text descriptions.
3. **Storage**: Writes cropped PNG image file to MinIO/S3 object storage under path `{tenant_id}/{doc_id}/{img_id}.png`.
