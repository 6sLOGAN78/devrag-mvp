# Beginner Path: Fundamentals of RAGFlow

## Target Audience
Developers or architects new to RAGFlow who want to understand high-level system concepts, set up the development environment, navigate the codebase, and understand core API workflows.

---

## Learning Objectives
1. Understand RAGFlow's core value proposition: vision-based document parsing + hybrid retrieval + visual agent canvas.
2. Build and run RAGFlow locally using Docker Compose or source code.
3. Understand the multi-tenant model (`User` -> `UserTenant` -> `Tenant` -> `Knowledgebase`).
4. Perform basic REST API calls for dataset creation, document upload, and chat completion.

---

## Primary Reading List

1. **System Overview**: Read [21-end-to-end-flows/ragflow-one-request.md](../21-end-to-end-flows/ragflow-one-request.md).
2. **User Registration & Login**: Read [21-end-to-end-flows/user-registration.md](../21-end-to-end-flows/user-registration.md) and inspect [api/apps/restful_apis/user_api.py](file:///home/logan78/Desktop/ragflow/api/apps/restful_apis/user_api.py#L61).
3. **Knowledge Base Creation**: Read [21-end-to-end-flows/create-knowledge-base.md](../21-end-to-end-flows/create-knowledge-base.md).
4. **Document Upload**: Read [21-end-to-end-flows/upload-document.md](../21-end-to-end-flows/upload-document.md).
5. **Frontend Architecture**: Inspect [web/src/routes.tsx](file:///home/logan78/Desktop/ragflow/web/src/routes.tsx#L1) and page components in `web/src/pages/`.

---

## Hands-On Milestones

- **Milestone 1**: Register a user via UI, log in, inspect `user` and `tenant` tables in MySQL.
- **Milestone 2**: Create a Knowledge Base via `POST /v1/dataset`, inspect indices in Elasticsearch (`ragflow_*`).
- **Milestone 3**: Upload a PDF file, check object storage location in MinIO console.
