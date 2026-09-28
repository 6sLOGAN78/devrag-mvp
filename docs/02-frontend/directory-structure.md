# Frontend Directory Structure

## Level 1: Workspace Organization

The `web/` directory contains the full frontend workspace, including package configuration, build scripts, asset pipelines, and source files under `web/src/`.

---

## Level 2: Complete `web/src/` Source Tree

```
web/src/
├── app.tsx                         # Root React application wrapper & i18n mounting
├── routes.tsx                      # React Router 7 route definitions & lazy loading logic
├── assets/                         # SVG icons, banner graphics, Inter font files
├── components/                     # Reusable UI component library
│   ├── api-service/                # API token management modal
│   ├── canvas/                     # Workflow canvas helpers & node connectors
│   ├── chunk-method-dialog/        # Document chunking strategy modal
│   ├── document-preview/           # Multi-format document chunk previewer
│   ├── llm-select/                 # LLM provider & model selection dropdown
│   ├── llm-setting-items/          # Temperature, top_p, max_tokens settings drawer
│   ├── markdown-content/           # Markdown & LaTeX rendering component
│   ├── similarity-slider/          # Vector similarity threshold slider
│   └── ui/                         # Base Shadcn/Radix UI primitive components
├── constants/                      # Enums, API paths, chunk parsing defaults
├── hooks/                          # Custom React hooks & Zustand stores
│   ├── auth-hooks.ts               # Login, logout, user profile hooks
│   ├── use-agent-request.ts        # Agent flow creation & execution hooks
│   ├── use-document-request.ts     # Document upload & chunk management hooks
│   └── use-knowledge-request.ts    # Dataset CRUD hooks
├── interfaces/                     # TypeScript interface definitions & DB response schemas
├── layouts/                        # Base page layouts (Header, Sidebar, Navigation)
├── locales/                        # Internationalization JSON files (zh, en, es, fr, ja, etc.)
├── pages/                          # Application pages
│   ├── admin/                      # Enterprise admin dashboard pages
│   ├── agent/                      # Agent canvas editor & execution log pages
│   ├── datasets/                   # Knowledge base (Dataset) listing & management pages
│   ├── next-chats/                 # Multi-modal chat playground & shared chat pages
│   ├── login-next/                 # User authentication (Login & Register) pages
│   └── user-setting/               # User profile, API keys, team management, model settings
├── services/                       # Low-level REST API service functions
└── utils/                          # Common helpers (authorization-util.ts, formatters)
```

### Primary Directory References

- Route Table: [`web/src/routes.tsx`](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L28)
- UI Components: [`web/src/components/`](file:///home/logan78/Desktop/ragflow/web/src/components)
- Custom Hooks: [`web/src/hooks/`](file:///home/logan78/Desktop/ragflow/web/src/hooks)
- Pages: [`web/src/pages/`](file:///home/logan78/Desktop/ragflow/web/src/pages)
- Auth Utilities: [`web/src/utils/authorization-util.ts`](file:///home/logan78/Desktop/ragflow/web/src/utils/authorization-util.ts)
