# Frontend Architecture

## Level 1: Conceptual System Architecture

The frontend architecture follows modern component-driven SPA paradigms. It leverages React 18 for concurrent UI rendering, React Router 7 for route matching and code-splitting, Zustand for store state, TailwindCSS for styling, and custom TanStack React Query / Axios hooks for asynchronous data synchronization.

---

## Level 2: Architectural Layers & Source Map

```
+-----------------------------------------------------------------------------------+
| 1. VIEW LAYER (React 18 SPA)                                                       |
|    Pages (pages/), Canvas (@xyflow/react), Reusable UI Components (components/)   |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
| 2. STATE MANAGEMENT & CUSTOM HOOKS                                                |
|    Zustand Stores (hooks/), Custom Data Hooks (hooks/use-*-request.ts)             |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
| 3. API SERVICE LAYER & NETWORK INTERCEPTOR                                        |
|    Axios HTTP Client (utils/api.ts / services/), Authorization Header Injector     |
+-----------------------------------------------------------------------------------+
                                         |
                                    REST / SSE
                                         |
+-----------------------------------------------------------------------------------+
| 4. BACKEND ROUTING GATEWAY (Go Gin :9380 / Python Quart :9380)                     |
+-----------------------------------------------------------------------------------+
```

### Architectural Layer Details

1. **Routing & Code-Splitting**:
   All routes are defined in [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28) using React Router 7's `createBrowserRouter`. Lazy component loading is handled by `withLazyRoute` ([`web/src/routes.tsx:L112`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L112)), wrapping components in `<Suspense fallback={...}>`.

2. **Authentication Interceptor**:
   [`web/src/utils/authorization-util.ts`](file:///home/logan78/Desktop/ragflow/web/src/utils/authorization-util.ts) manages access tokens in `localStorage`. Request interceptors auto-inject `Authorization: Bearer <token>` into outgoing requests. Upon receiving HTTP 401, the response interceptor clears the token and triggers a redirect to `/login-next`.

3. **State Management Strategy**:
   - Component Local State: React `useState` / `useReducer` for ephemeral UI state.
   - Global App State: Zustand stores (`useUserSettingStore`, `useAgentStore`, `useChatStore`).
   - Server State: React Query hooks wrapped inside `web/src/hooks/`.

4. **Visual Canvas Subsystem**:
   Located in [`web/src/pages/agent/canvas/`](file:///home/logan78/Desktop/ragflow/web/src/pages/agent/canvas), built on top of `@xyflow/react`. Handles node dragging, edge connections, operator configuration drawers, execution state animations, and node debug logs.
