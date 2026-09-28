# 02-Auth-UI

## 1. Objective
To build the unauthenticated pages where a user can register for a new account or log in to an existing one, and store the resulting JWT.

## 2. Documentation Basis
*   `ragflow-docs/16-auth/authentication.md`: DOCUMENTED - The system relies on email/password login resulting in a token.

## 3. Prerequisites
*   `01-Frontend-Core` (Router and API Client).
*   Backend Part 03 (Auth APIs must be running).

## 4. Components to Implement
*   **Login Page**: Route `/login`.
*   **Register Page**: Route `/register`.
*   **Auth Context**: React Context to hold the current user state globally.

---

## Page: Login Page

### 1. Page Purpose
Authenticates returning users.

### 2. Route
`/login`

### 3. Access Requirements
*   Only accessible to unauthenticated users. If an authenticated user visits, redirect to `/dashboard`.

### 4. Page Layout
*   Centered card on a solid or gradient background.
*   No Sidebar or App Shell (this is a public route).

### 5. Visual Components
*   **Card Container**: Holds the form.
*   **Email Input**: Text field.
*   **Password Input**: Masked text field.
*   **Submit Button**: "Sign In" button with loading spinner state.
*   **Link**: "Don't have an account? Register."

### 6. Component Hierarchy
`PROPOSED`:
```text
LoginView
└── AuthCard
    ├── Title ("Sign in to devRAG")
    ├── ErrorAlert (Hidden by default)
    ├── LoginForm
    │   ├── Input[email]
    │   ├── Input[password]
    │   └── SubmitButton
    └── RegisterLink
```

### 7. User Interactions
*   User types email and password.
*   User clicks Submit.
*   UI shows loading state.
*   If error (e.g. 401), show red `ErrorAlert`.
*   If success, save token and redirect to `/dashboard`.

### 8. Frontend State
*   Local state: `email`, `password`, `isLoading`, `errorMessage`.
*   Global state update on success: `setAuthToken(token)`.

### 9. API Contract
*   **Endpoint**: `POST /api/login` (DOCUMENTED)
*   **Request**: `{"email": "...", "password": "..."}`
*   **Success Response**: `{"token": "ey..."}`

### 10. Expected UI States
*   **Loaded**: Form is ready.
*   **Loading**: Button is disabled, spinner visible.
*   **Error**: Red text banner explaining the failure.

### 11. Responsive Behavior
*   Card takes up 90% width on mobile, max-width 400px on desktop.

### 12. Accessibility
*   Inputs must have `<label>` tags.
*   Form must submit on `Enter` key press.

### 13. Verification
1.  Open `/login`.
2.  Enter bad credentials. Verify error message appears.
3.  Enter good credentials. Verify redirection to `/dashboard`.

### 14. Acceptance Criteria
*   [ ] JWT is successfully stored in LocalStorage.
*   [ ] Redirection works.
*   [ ] Error handling is graceful.

---

## 5. Detailed Sequential Implementation Steps

### Step 01: Build Global Auth Context

#### What I Implement
Create `src/context/AuthContext.tsx`. Create a Provider that checks `localStorage.getItem('token')` on mount. Expose `isAuthenticated`, `token`, `login(token)`, and `logout()` functions via React Context.

#### What the User Sees
No visual changes yet.

#### What the Frontend Receives
Token from LocalStorage on mount.

#### What the Frontend Does
Provides global state to the React component tree.

#### What the User Can Do
N/A.

#### What the Backend Must Provide
N/A.

#### Expected Output
Any component can call `useAuth()` to check if the user is logged in.

#### Verification
Ensure the Context compiles and wraps your `<App />`.

---

### Step 02: Implement Protected Routing

#### What I Implement
In your Router configuration, create a `<ProtectedRoute>` wrapper component. If `isAuthenticated` is false, return `<Navigate to="/login" />`. Wrap the `AppShell` route with this component.

#### What the User Sees
When navigating to `/dashboard`, the screen instantly redirects to `/login`.

#### What the Frontend Receives
A route change event.

#### What the Frontend Does
Evaluates the auth state. Redirects if unauthorized.

#### What the User Can Do
Only access public routes.

#### What the Backend Must Provide
N/A.

#### Expected Output
Routing security is enforced on the client side.

#### Verification
Visit `/dashboard` manually in the address bar and verify it kicks you to `/login`.

---

### Step 03: Build the Login View

#### What I Implement
Create `src/pages/Login.tsx`. Implement the HTML/CSS for the centered card. Wire the form inputs to React state. Write the `onSubmit` handler to call `apiClient.post('/api/login')`.

#### What the User Sees
A centered login card with email and password inputs, a submit button, and optional error banners.

#### What the Frontend Receives
User input (keystrokes) and HTTP Response (JSON containing a JWT or Error message).

#### What the Frontend Does
1. Form submit triggers `e.preventDefault()`.
2. Set `isLoading(true)`.
3. Await POST call.
4. If success: call `login(response.token)` from AuthContext, then `navigate('/dashboard')`.
5. If error: set `errorMessage('Invalid credentials')`.
6. Set `isLoading(false)`.

#### What the User Can Do
Type credentials and submit the form. See loading indicators.

#### What the Backend Must Provide
`POST /api/login` accepting `email` and `password`, returning a JSON token on success or a `401` on failure.

#### Expected Output
A fully functioning login interface that seamlessly drops the user into the protected app shell upon success.

#### Verification
Ensure backend is running. Test the form end-to-end with both valid and invalid credentials.
