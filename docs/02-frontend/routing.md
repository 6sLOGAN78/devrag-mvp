# Frontend Routing Architecture

## Level 1: Route Mechanics & Lazy Loading

RAGFlow frontend uses **React Router v7** (`createBrowserRouter`) defined in [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28).

The routing system provides:
1. **Dynamic Code Splitting**: Route components are dynamically imported using `withLazyRoute` ([`web/src/routes.tsx:L112`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L112)), loading JavaScript chunks on demand to minimize initial load size.
2. **Layout Wrappers**: Standard routes are wrapped inside layout components (e.g., standard layout with top navigation header or full-bleed canvas layout).
3. **Public Share Routes**: Dedicated unauthenticated share routes for shared agents (`/agent/share`) and shared chat widgets (`/chats/share`, `/chats/widget`).
4. **Authentication Guards**: Route transitions inspect access tokens stored via [`web/src/utils/authorization-util.ts`](file:///home/logan78/Desktop/ragflow/web/src/utils/authorization-util.ts), redirecting unauthenticated users to `/login-next`.

---

## Level 2: Complete Route Definition Table

| Route Path (`Routes` Enum) | Associated Component Path | Layout | Auth Required | Description |
| :--- | :--- | :--- | :--- | :--- |
| `/login` / `/login-next` | `@/pages/login-next` | `false` | No | User authentication & registration page |
| `/home` | `@/pages/home` | `true` | Yes | System dashboard & summary |
| `/datasets` | `@/pages/datasets` | `true` | Yes | Knowledge bases (datasets) list page |
| `/dataset/files` | `@/pages/dataset` | `true` | Yes | Document file listing in dataset |
| `/agent` | `@/pages/agent/canvas` | `false` | Yes | Visual Agent workflow canvas |
| `/agents` | `@/pages/agents` | `true` | Yes | List of user agents & templates |
| `/chats` / `/chat` | `@/pages/next-chats` | `true` | Yes | Interactive chat playground |
| `/chats/share` | `@/pages/next-chats/share` | `false` | No | Public shared chat interface |
| `/agent/share` | `@/pages/agent/share` | `false` | No | Public shared agent execution interface |
| `/user-setting/profile` | `@/pages/user-setting` | `true` | Yes | User settings & model provider config |
| `/admin/users` | `@/pages/admin` | `true` | Yes | Enterprise admin user management |
| `/admin/services` | `@/pages/admin` | `true` | Yes | Enterprise admin system status |

### Code Implementation Snapshot

```typescript
// web/src/routes.tsx (Line 112)
const withLazyRoute = (
  importer: () => Promise<{ default: React.ComponentType<any> }>,
  fallback: React.ReactNode = defaultRouteFallback,
) => {
  const LazyComponent = lazy(importer);
  const Wrapped: React.FC<any> = (props) => (
    <Suspense fallback={fallback}>
      <LazyComponent {...props} />
    </Suspense>
  );
  return process.env.NODE_ENV === 'development' ? LazyComponent : memo(Wrapped);
};
```
