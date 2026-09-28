# 03-KB-Dashboard

## 1. Objective
To build the primary landing page for authenticated users, allowing them to view, create, and manage their Knowledge Bases.

## 2. Documentation Basis
*   `ragflow-docs/04-api/knowledge-base.md`: DOCUMENTED - KBs are the primary organizational unit.

## 3. Prerequisites
*   `01-Frontend-Core` (App Shell).
*   `02-Auth-UI` (Logged in user).
*   Backend Part 04 (KB CRUD APIs).

## 4. Components to Implement
*   **Dashboard Page**: Route `/dashboard`.
*   **KB Card Component**: Visual representation of a KB.
*   **Create KB Modal**: Form dialog to create a new KB.

---

## Page: Dashboard (KB List)

### 1. Page Purpose
Provides an overview of all user data containers.

### 2. Route
`/dashboard`

### 3. Access Requirements
*   Valid JWT required. Renders inside `AppShell`.

### 4. Page Layout
*   **Header**: Title "Knowledge Bases" and a primary "Create Knowledge Base" button aligned right.
*   **Content**: A CSS Grid of Cards representing individual KBs.

### 5. Visual Components
*   **PageHeader**: Contains title and action button.
*   **KBGrid**: A responsive grid (`grid-cols-1 md:grid-cols-3`).
*   **KBCard**: Displays `name`, `description`, `created_at`, and a "Delete" icon.
*   **CreateModal**: An overlay dialog containing a form.
*   **EmptyState**: A friendly message and CTA if the user has 0 KBs.

### 6. Component Hierarchy
`PROPOSED`:
```text
DashboardView
├── PageHeader
│   └── CreateButton
├── CreateKBModal (Hidden)
│   └── Form (Name, Desc)
└── KBGrid
    ├── KBCard
    ├── KBCard
    └── ...
```

### 7. User Interactions
*   Click "Create Knowledge Base" -> Modal opens.
*   Submit Modal Form -> API called -> Modal closes -> Grid refreshes.
*   Click on a KBCard -> Navigates to `/dashboard/kb/:id` (Document Management).
*   Click Delete icon on Card -> Shows confirmation dialog -> API called -> Grid refreshes.

### 8. Frontend State
*   `kbs`: Array of Knowledge Base objects.
*   `isModalOpen`: Boolean.
*   `isLoading`: Boolean for initial fetch.

### 9. API Contract
*   **List API**: `GET /api/knowledge-base` -> Returns `[{id, name, description}]`.
*   **Create API**: `POST /api/knowledge-base` -> Returns `{id, name, description}`.
*   **Delete API**: `DELETE /api/knowledge-base/:id` -> Returns 200 OK.

### 10. Expected UI States
*   **Loading**: Grid of skeleton cards.
*   **Empty**: Illustration prompting user to create their first KB.
*   **Populated**: Grid of interactive cards.

### 11. Responsive Behavior
*   Grid falls back to 1 column on mobile screens.

### 12. Accessibility
*   Modal must trap focus (user cannot tab behind the modal while open).
*   Modal must close on `Escape` key.

### 13. Verification
1.  Log in.
2.  Observe empty state.
3.  Click Create. Fill out form. Submit.
4.  Observe modal close and new card appear in the grid.
5.  Click card to verify navigation works.

### 14. Acceptance Criteria
*   [ ] Fetches KBs on mount.
*   [ ] Creation form works and updates UI optimistically or via refetch.
*   [ ] Layout matches specifications.

---

## 5. Detailed Sequential Implementation Steps

### Step 01: Build the Dashboard UI

#### What I Implement
Create `src/pages/Dashboard.tsx`. Stub out the `KBGrid` and `KBCard` components using mock data. Implement the CSS Grid layout. Add the Page Header.

#### What the User Sees
A grid of fake Knowledge Bases and a title header.

#### What the Frontend Receives
User clicks (navigation only).

#### What the Frontend Does
Renders static HTML/CSS.

#### What the User Can Do
View the layout to ensure it looks correct.

#### What the Backend Must Provide
N/A.

#### Expected Output
You can navigate to `/dashboard` and see mock data laid out nicely.

#### Verification
Visually inspect the route.

---

### Step 02: Integrate the GET API

#### What I Implement
Add a `useEffect` hook (or use React Query) to call `apiClient.get('/api/knowledge-base')` when the component mounts. Update the local state with the result. Replace mock data with the `kbs` state array.

#### What the User Sees
A loading skeleton, followed by the real KBs owned by their tenant.

#### What the Frontend Receives
JSON array of KBs from the backend.

#### What the Frontend Does
Iterates over the JSON array and renders a `KBCard` for each item. Displays the Empty State component if the array is empty.

#### What the User Can Do
See their existing data.

#### What the Backend Must Provide
`GET /api/knowledge-base` returning JSON. Must enforce tenant isolation via the JWT.

#### Expected Output
Real data is rendered in the UI.

#### Verification
Ensure the backend is running. The page should show KBs created by this user via Postman in earlier parts.

---

### Step 03: Implement the Create Modal

#### What I Implement
Build the modal component. Wire its visibility to a state variable (`isModalOpen`). Connect the form submission to `apiClient.post('/api/knowledge-base')`. On success, append the new KB to the local state array (or trigger a refetch).

#### What the User Sees
An overlay dialog darkening the background, containing a form for "Name" and "Description".

#### What the Frontend Receives
User input strings. JSON response from backend.

#### What the Frontend Does
POSTs the data. Upon 200 OK, closes the modal and updates the DOM to include the new card.

#### What the User Can Do
Create new KBs entirely via the UI.

#### What the Backend Must Provide
`POST /api/knowledge-base` accepting `name` and `description`.

#### Expected Output
A seamless creation experience.

#### Verification
Create a KB via the UI, verify it appears, and refresh the page to ensure it persisted to the database.
