# Subpart 03: OCR and TSR

## 1. Objective
To extract text from the sorted bounding boxes using OCR, and specifically convert tables into Markdown representations using Table Structure Recognition.

## 2. Documentation Basis
*   `docs/06-document-processing/vision-models.md`: DOCUMENTED - PaddleOCR.

## 3. Prerequisites
*   `02-Layout-Analysis` (Sorted Bounding Boxes).

## 4. Components to Implement
*   **Image Cropper**: Slices the original image based on bounding boxes.
*   **PaddleOCR Client**: Runs text extraction.
*   **Content Merger**: Concatenates everything back into chunks.

## 5. Detailed Sequential Implementation Steps

### Step 01: Crop and OCR

#### Purpose
Extract text block by block.

#### Prerequisites
PaddleOCR installed locally or via API.

#### Implementation Scope
Iterate through the sorted bounding boxes.
1. Crop the PIL Image using the coordinates.
2. If class is "paragraph" or "title", pass the crop to PaddleOCR. Append the resulting string to an array.
3. If class is "image", ignore it (or pass it to a multimodal LLM for captioning if desired).
4. If class is "table", pass it to a TSR model (or a multimodal LLM) to get a Markdown grid. Append the grid to the array.

#### Outputs
An array of ordered strings (representing the document text).

#### Proceed When
Text and tables are extracted successfully.

### Step 02: Handoff to Embedding Pipeline

#### Purpose
Ingest the results.

#### Prerequisites
Step 01.

#### Implementation Scope
Join the array of strings into larger chunks (~500 tokens). Send these chunks to the Embedding API (Part 05.03) and insert them into the Vector DB.

#### Outputs
Vector DB records.

#### Expected Result
DeepDoc pipeline is complete.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Upload a complex PDF via the API. Verify that the Vector DB contains clean text without header/footer noise.

#### Proceed When
End-to-end PDF processing works.

