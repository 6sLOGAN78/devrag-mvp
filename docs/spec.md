# Project Implementation Specification

## Source of Truth

The `docs/` directory is the authoritative source of truth for this project.

Everything described in `docs/` should be treated as the intended architecture, functionality, behavior, system design, data flow, components, and implementation requirements.

Before implementing any feature, read the relevant documentation from `docs/`.

Do not redesign, simplify, replace, or ignore documented architecture unless the documentation contains a genuine contradiction or an implementation blocker.

If there is a conflict between this specification, another repository, and the `docs/` directory:

**`docs/` always wins.**

---

## Primary Goal

Build the complete system described in `docs/`.

The objective is not to produce a minimal demo or partial prototype.

Implement all reasonably implementable components, services, flows, features, interfaces, and integrations defined by the documentation.

Avoid:

- placeholder implementations
- fake data where real implementation is expected
- empty functions
- TODO-only implementations
- mocked functionality presented as completed functionality
- silently skipping difficult features

If something genuinely cannot be implemented, document the blocker clearly rather than pretending it is complete.

---

## Reference Repository: RAGFlow

A local RAGFlow repository is available at:

`~/desktop x/ragflow`

This repository is a **reference implementation only**.

Use it when useful for understanding mature implementation patterns such as:

- repository and folder organization
- service boundaries
- backend architecture
- RAG pipeline organization
- document ingestion
- parsing
- chunking
- embeddings
- indexing
- retrieval
- reranking
- knowledge-base management
- API organization
- task/worker architecture
- frontend architecture
- UI flows
- component organization
- state management
- document-management UX
- chat/RAG UX
- production engineering patterns

Do not blindly copy RAGFlow.

Adapt useful patterns to the architecture defined in `docs/`.

If RAGFlow's implementation conflicts with `docs/`, follow `docs/`.

---

## Folder Structure

First inspect `docs/` and derive the folder structure required by the documented architecture.

If the documentation fully specifies the structure, follow it exactly.

If some parts of the folder structure are unspecified, inspect:

`~/desktop x/ragflow`

and use its architecture as inspiration for a scalable, production-quality structure.

When choosing an unspecified structure:

1. Prefer clear separation of concerns.
2. Keep modules cohesive.
3. Avoid unnecessary abstraction.
4. Keep future extensibility in mind.
5. Follow the technologies and architectural boundaries defined in `docs/`.
6. Do not introduce major frameworks or architectural patterns purely because RAGFlow uses them.

---

## Frontend

For frontend implementation, use the RAGFlow repository as a major reference:

`~/desktop x/ragflow`

Study its frontend to understand:

- application layout
- navigation
- knowledge-base workflows
- document management
- ingestion flows
- chat interfaces
- retrieval configuration
- component hierarchy
- reusable UI patterns
- state management
- loading states
- error states
- empty states
- user feedback
- responsive behavior

Build a polished, complete frontend appropriate for this project's functionality.

Do not simply clone RAGFlow's visual appearance.

The frontend must represent **this project's own architecture and features as specified in `docs/`**.

Reuse concepts and interaction patterns where useful, but adapt them to this project.

---

## Implementation Strategy

Before writing substantial code:

1. Read this `spec.md`.
2. Read the complete `docs/` directory.
3. Understand the end-to-end architecture.
4. Identify dependencies between components.
5. Inspect the relevant parts of `~/desktop x/ragflow` when additional implementation guidance is useful.
6. Create a dependency-aware implementation plan.
7. Implement the system incrementally.
8. Validate every major phase before moving forward.

Do not begin by generating a large number of disconnected files.

Understand the architecture first.

---

## Architecture Discipline

Maintain the architecture described in `docs/`.

Before introducing:

- a new service
- a new database
- a new queue
- a new framework
- a new abstraction layer
- a different API structure
- a different RAG pipeline
- a different storage model

verify that it is consistent with the documented architecture.

If an architectural decision is not specified, make the smallest reasonable production-quality decision and document it.

Use RAGFlow as supporting evidence for such decisions where appropriate.

---

## Backend Quality

Backend implementation should be production-oriented.

Where applicable, include:

- clear module boundaries
- typed interfaces
- configuration management
- environment-variable handling
- input validation
- structured error handling
- structured logging
- database migrations
- transaction handling
- async processing where appropriate
- retries where appropriate
- timeout handling
- idempotency where required
- graceful failure handling
- API validation
- health checks
- clean dependency management

Avoid giant files and tightly coupled modules.

---

## RAG / AI Pipeline

For RAG-related functionality, implement the complete pipeline required by `docs/`.

Depending on the documented architecture, this may include:

- document upload
- document parsing
- preprocessing
- chunking
- metadata extraction
- embeddings
- indexing
- vector storage
- lexical/hybrid retrieval
- filtering
- reranking
- context construction
- model invocation
- citation/source tracking
- knowledge-base management
- retrieval configuration
- evaluation
- background processing

Use RAGFlow to study mature approaches where useful, but follow this project's documented requirements.

---

## Testing

Testing is part of implementation, not an optional final step.

Add appropriate:

- unit tests
- integration tests
- API tests
- database tests
- pipeline tests
- frontend tests where valuable

Each implementation phase should end in a working state.

Do not knowingly move forward with broken tests unless the failure is explicitly documented as a blocked dependency.

---

## Verification

A feature is not complete merely because code exists.

Verify that:

- the code runs
- imports resolve
- dependencies are correctly configured
- tests pass
- APIs work
- frontend and backend communicate correctly
- database operations work
- RAG flows work end-to-end
- error cases are handled
- documented acceptance requirements are satisfied

Where possible, test functionality using realistic execution rather than static inspection alone.

---

## Documentation

Keep project documentation synchronized with implementation.

When implementation introduces an important decision not explicitly covered in `docs/`, document:

- the decision
- why it was necessary
- how it fits the existing architecture

Do not silently diverge from the documented design.

---

## Priority Order

Whenever instructions or references conflict, use this priority:

1. `docs/` — authoritative architecture and requirements
2. this `spec.md` — implementation rules
3. existing project code that is confirmed correct
4. `~/Desktop/x/ragflow` — reference implementation and inspiration
5. general engineering judgment

RAGFlow must never override an explicit decision from `docs/`.

---

## Completion Criteria

The project should only be considered complete when:

1. All required architecture from `docs/` has been implemented.
2. All major documented features are functional.
3. Backend and frontend are integrated.
4. Required RAG/AI flows work end-to-end.
5. Persistent storage and external integrations work as intended.
6. Tests for critical functionality pass.
7. The application can be run using documented setup instructions.
8. There are no critical placeholder implementations.
9. There are no major undocumented deviations from `docs/`.
10. Important error and failure paths are handled.
11. The frontend provides usable access to the implemented functionality.
12. The implementation has been verified against the original documentation.

The goal is a **complete, coherent, production-quality implementation of the architecture described in `docs/`**, using RAGFlow only as a reference wherever the documentation leaves implementation details open.
