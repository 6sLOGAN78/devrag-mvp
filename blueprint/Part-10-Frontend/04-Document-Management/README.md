# 04-Document-Management

## 1. Objective
To build the interface where users manage a specific Knowledge Base, upload raw files, and monitor the asynchronous parsing/chunking pipeline.

## 2. Documentation Basis
*   `docs/06-document-processing/upload.md`: DOCUMENTED - File upload.
*   `docs/10-cache-and-queues/workers.md`: INFERRED - The UI must poll or use websockets to detect when the background worker finishes processing.

## 3. Prerequisites
*   `03-KB-Dashboard` (Navigation to this route).
*   Backend Part 05 (Upload API and Background Workers must be fully functional).

## 4. Components to Implement
*   **KB Detail Page**: Route `/dashboard/kb/:id`.
*   **Upload Area**: Drag-and-drop zone.
*   **Document List**: Data table showing file status.

---

## Page: KB Detail (Document List)

### 1. Page Purpose
Manage the documents within a specific KB.

### 2. Route
`/dashboard/kb/:id`

### 3. Access Requirements
*   Valid JWT. Renders inside `AppShell`.

### 4. Page Layout
*   **Breadcrumb Header**: `Dashboard > [KB Name]`.
*   **Top Section**: A dashed-border Drag-and-Drop upload zone.
*   **Bottom Section**: A Data Table listing existing documents.

### 5. Visual Components
*   **Dropzone**: Accepts file drops or clicks to open system file dialog.
*   **DocumentTable**: Columns: `Filename`, `Upload Date`, `Status`, `Tokens`, `Actions`.
*   **StatusBadge**: Visual indicator (Gray `Unstart`, Blue `Running`, Green `Done`, Red `Failed`).

### 6. Component Hierarchy
`PROPOSED`:
```text
KBDetailView
├── Breadcrumbs
├── UploadDropzone
└── DocumentTable
    ├── TableHeader
    └── TableRow (maps over documents)
        └── StatusBadge
```

### 7. User Interactions
*   User drops a file -> UI shows a local progress bar while uploading to API.
*   Upload finishes -> File appears in Table with status `Unstart`.
*   Background polling starts -> Status updates to `Running` then `Done`.

### 8. Frontend State
*   `documents`: Array of document objects.
*   `uploadProgress`: Number (0-100).
*   **Polling State**: A timer or React Query instance that fetches the document list every 3 seconds if any document is in `Unstart` or `Running` state.

### 9. API Contract
*   **List API (PROPOSED)**: `GET /api/kb/:id/documents` -> Returns `[{id, file_name, status, ...}]`. *(Note: You must build this simple GET endpoint on your backend if you haven't already).*
*   **Upload API**: `POST /api/document/upload` (`multipart/form-data`).

### 10. Expected UI States
*   **Polling**: Background refresh is invisible except for the `StatusBadge` changing colors.

### 11. Responsive Behavior
*   Table scrolls horizontally on mobile devices.

### 12. Accessibility
*   Table headers must use `<th>`.
*   Dropzone must be focusable and operable via `Enter` key.

### 13. Verification
1.  Navigate into a KB.
2.  Upload a `.txt` file.
3.  Watch the table. The status should automatically change from `Unstart` -> `Done` without refreshing the page manually.

### 14. Acceptance Criteria
*   [ ] File upload sends `multipart/form-data`.
*   [ ] Polling logic starts and stops correctly.
*   [ ] Table renders status badges accurately.

---

## 5. Detailed Sequential Implementation Steps

### Step 01: Build the Layout and Fetch List

#### What I Implement
Create `src/pages/KBDetail.tsx`. Implement the route param extraction (`useParams()` for `:id`). Fetch the list of documents for this KB on mount. Render the `DocumentTable`.

#### What the User Sees
A table containing any files previously uploaded to this KB.

#### What the Frontend Receives
JSON array of documents.

#### What the Frontend Does
Parses the `:id` from the URL, fetches the documents, and renders the HTML table.

#### What the User Can Do
View their files.

#### What the Backend Must Provide
`GET /api/kb/:id/documents`

#### Expected Output
A static view of current documents.

#### Verification
Navigate to the route and ensure mock or existing data loads.

---

### Step 02: Implement the Uploader

#### What I Implement
Add an `<input type="file" />` disguised as a drag-and-drop zone. On change, grab the `File` object. Create a `FormData` object, append the file and the `kb_id`. Use `apiClient.post('/api/document/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })`.

#### What the User Sees
A dashed box that they can drag a file into. A loading bar appears upon drop.

#### What the Frontend Receives
A local `File` object from the browser API.

#### What the Frontend Does
Serializes the file to `multipart/form-data` and POSTs it. Upon success, refetches the document list.

#### What the User Can Do
Upload raw data to the backend.

#### What the Backend Must Provide
`POST /api/document/upload` (from Part 05).

#### Expected Output
The uploaded file appears in the table with status `Unstart`.

#### Verification
Upload a small `.txt` file and check the Network tab.

---

### Step 03: Implement Status Polling

#### What I Implement
Write a `useEffect` that checks the current `documents` array. If *any* document has `status === 'UNSTART'` or `status === 'RUNNING'`, set a `setInterval` to fetch the document list again every 3000ms. Clear the interval when all documents reach `DONE` or `FAILED`, or when the component unmounts.

#### What the User Sees
The Status badge on the newly uploaded file magically changes colors (Gray -> Blue -> Green) without the user refreshing the page.

#### What the Frontend Receives
Repeated JSON arrays from the backend every 3 seconds.

#### What the Frontend Does
Diffs the old state against the new state. If the status changed, React re-renders just the badge.

#### What the User Can Do
Watch the pipeline process their file in real-time.

#### What the Backend Must Provide
Fast, lightweight responses to `GET /api/kb/:id/documents` that accurately reflect the database state updated by the Background Worker (Part 05.02).

#### Expected Output
Real-time UI updates mirroring background worker progress.

#### Verification
Upload a file. Do not touch the mouse. Watch the status transition automatically.
