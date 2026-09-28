# 01-Frontend-Core

## 1. Objective
To initialize the frontend project, install the necessary routing and state management dependencies, configure the global API client (to inject JWTs), and establish the structural Application Shell (Sidebar + Topbar).

## 2. Documentation Basis
*   `docs/02-frontend/architecture.md`: INFERRED - The docs mention standard SPA architecture, but exact tooling is unspecified.
*   **PROPOSED**: Use React with React Router, Tailwind CSS for styling, and a pre-built component library (like shadcn/ui or MUI) to accelerate development.

## 3. Prerequisites
*   Node.js installed locally.
*   Backend API running on `localhost:8000` (for eventual proxying).

## 4. Components to Implement
*   **Project Skeleton**: `package.json`, `index.html`.
*   **API Interceptor**: A global `fetch` or `axios` instance.
*   **App Router**: Central route definitions.
*   **Application Shell Component**: The visual wrapper for protected routes.

---

## Page: Application Shell (Shared Layout)

### 1. Page Purpose
Provides consistent global navigation, user context, and layout structure for all authenticated pages in the application.

### 2. Route
`PROPOSED`: Wrapper for `/dashboard/*`, `/chat/*`.

### 3. Access Requirements
*   Authentication requirement: Valid JWT required.

### 4. Page Layout
*   **Desktop layout**: A fixed left Sidebar (250px width) containing primary navigation links. A fixed Top Header containing the active workspace/tenant name and user profile dropdown. A dynamic Main Content region that scrolls independently.
*   **Tablet/Mobile layout**: Sidebar collapses into a hamburger menu.

### 5. Visual Components
*   **SidebarNav**: Links to "Knowledge Bases", "Chat", "Settings".
*   **TopHeader**: Displays current Tenant context.
*   **UserAvatar**: Dropdown for "Log Out".
*   **MainOutlet**: The React Router `<Outlet />` where child pages render.

### 6. Component Hierarchy
`PROPOSED`:
```text
ApplicationShell
├── SidebarNav
│   └── NavLinks
├── TopHeader
│   ├── TenantSelector
│   └── UserDropdown
└── MainOutlet
```

### 7. User Interactions
*   Clicking a Sidebar link updates the route and changes the active page.
*   Clicking "Log Out" clears local storage and redirects to `/login`.

### 8. Frontend State
*   **Auth State**: Reads `isAuthenticated` from global context.
*   **Tenant State**: Reads `currentTenant` to display in the header.

### 9. API Contract
*   No specific API contract, though "Log Out" might hit a `POST /api/logout` if the backend tracks token invalidation (optional).

### 10. Expected UI States
*   **Loading**: Skeleton sidebar while validating user session.
*   **Loaded**: Full navigation visible.

### 11. Responsive Behavior
*   Sidebar hides behind a drawer button on screens < 768px.

### 12. Accessibility
*   Sidebar links must use `<nav>` tags and be reachable via Tab key.
*   Active route must be indicated visually and via `aria-current="page"`.

### 13. Verification
1.  Render the App Shell locally.
2.  Resize the browser window; verify the sidebar collapses.
3.  Click navigation links and ensure the URL changes without a full page reload.

### 14. Acceptance Criteria
*   [ ] Shell renders correctly.
*   [ ] Navigation links function.
*   [ ] Logout clears state.

---

## 5. Detailed Sequential Implementation Steps

### Step 01: Project Scaffolding

#### What I Implement
Run the scaffold command (e.g., `npx create-react-app frontend` or `npm create vite@latest frontend -- --template react-ts`). Install `react-router-dom` and your chosen UI library.

#### What the User Sees
A blank screen indicating the default server page.

#### What the Frontend Receives
Local compilation successful.

#### What the Frontend Does
Serves a static index file and boots up the React component tree.

#### What the User Can Do
Interact with the browser, though no UI exists yet.

#### What the Backend Must Provide
Nothing for this step.

#### Expected Output
A folder with `node_modules` and a `src/App.tsx` file. Running `npm run dev` starts a local server on port 3000/5173.

#### Verification
Open `http://localhost:5173`. You should see the default React/Vite screen.

---

### Step 02: Build the API Client

#### What I Implement
Create `src/api/client.ts`. Export a wrapper around `fetch` (or configure an Axios instance).

#### What the User Sees
No visual changes.

#### What the Frontend Receives
N/A

#### What the Frontend Does
1. Retrieve `token` from `localStorage`.
2. If token exists, append header: `Authorization: Bearer <token>`.
3. If response status is `401 Unauthorized`, automatically redirect the window to `/login`.

#### What the User Can Do
N/A

#### What the Backend Must Provide
Standard REST endpoints that require `Authorization` headers and return `401` when invalid.

#### Expected Output
A reusable function `apiClient.get('/api/me')` that handles auth transparently.

#### Verification
Unit test or manually inspect the code to ensure headers are injected.

---

### Step 03: Implement the Application Shell

#### What I Implement
Create `src/components/AppShell.tsx`. Implement the Sidebar, Header, and Main Content area using CSS Flexbox/Grid. Add `react-router-dom`'s `<Outlet />` inside the Main Content area.

#### What the User Sees
The main layout of the application: a left sidebar, top header, and empty main content area.

#### What the Frontend Receives
User clicks on navigation links.

#### What the Frontend Does
Changes the URL route without reloading the browser window.

#### What the User Can Do
Click links to navigate between empty pages.

#### What the Backend Must Provide
Nothing yet.

#### Expected Output
The UI skeleton is visible and routing functions correctly.

#### Verification
Mount the component in `App.tsx` temporarily to view it in the browser. Verify responsiveness on mobile viewports.
