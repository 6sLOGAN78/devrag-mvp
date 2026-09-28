# Subpart 02: Layout Analysis

## 1. Objective
To use a YOLO object detection model to identify the bounding boxes of paragraphs, headers, tables, and images on a page, allowing the system to understand the structural layout (e.g., 2-column formats) and avoid reading headers/footers.

## 2. Documentation Basis
*   `ragflow-docs/06-document-processing/vision-models.md`: DOCUMENTED - YOLO usage for layout.

## 3. Prerequisites
*   `01-PDF-to-Image` (Image objects).

## 4. Components to Implement
*   **YOLO Client**: Code to load a pre-trained YOLO model and run inference.
*   **Bounding Box Sorter**: Logic to determine reading order.

## 5. Detailed Sequential Implementation Steps

### Step 01: Run YOLO Inference

#### Purpose
Detect elements on the page.

#### Prerequisites
A downloaded YOLO model (e.g., `yolov8n` fine-tuned for documents). *IMPLEMENTATION DECISION: If you cannot host YOLO locally, use a cloud Vision API to mock this for now.*

#### Implementation Scope
Pass the PIL Image to the YOLO model. Extract the predictions.

#### Outputs
A list of bounding boxes `[ { "class": "title", "x1": 10, "y1": 20, "x2": 100, "y2": 50 }, ... ]`.

#### Proceed When
YOLO successfully returns coordinates.

### Step 02: Sort Bounding Boxes (Reading Order)

#### Purpose
Prevent text from jumping across columns.

#### Prerequisites
Step 01.

#### Implementation Scope
Implement a spatial sorting algorithm. Group boxes into columns based on their X coordinates, then sort top-to-bottom within those columns based on Y coordinates. Discard boxes classified as "header" or "footer".

#### Outputs
A sorted list of bounding boxes reflecting true reading order.

#### Expected Result
The system knows exactly what order to read the page in.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Draw the sorted numbers on a test image and save it to disk. Ensure a 2-column paper is numbered down the left column first, then the right column.

#### Proceed When
Reading order sorting is accurate.

