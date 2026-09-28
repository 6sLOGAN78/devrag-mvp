# Subpart 01: PDF to Image Rasterization

## 1. Objective
To convert a multi-page PDF document into an array of high-resolution images so that computer vision models can analyze them.

## 2. Documentation Basis
*   `docs/06-document-processing/vision-models.md`: DOCUMENTED - YOLO layout analysis operates on images, not native PDF text layers.

## 3. Prerequisites
*   Task Worker (Part 05.02) setup to intercept `.pdf` files.

## 4. Components to Implement
*   **Rasterizer**: A function wrapping `pdf2image` or `PyMuPDF`.

## 5. Detailed Sequential Implementation Steps

### Step 01: Implement Rasterizer

#### Purpose
Prepare the document for vision models.

#### Prerequisites
None.

#### Implementation Scope
Inside the task worker, check if the file extension is `.pdf`. If so, route it to a new `process_deepdoc()` function.
Use a library like `PyMuPDF` (`fitz`) to iterate through the PDF pages and render each page as a PNG image in memory.

#### Inputs
PDF bytes.

#### Outputs
Array of Image objects (e.g., PIL Images).

#### Expected Result
PDFs are successfully converted to arrays of images.

#### Verification
#### Acceptance Criteria
* [ ] Verifies correctly.
Temporarily save the first image to disk (`image.save('test.png')`) to ensure it looks correct and has sufficient DPI (e.g., 300 DPI).

#### Proceed When
Rasterization is reliable.

