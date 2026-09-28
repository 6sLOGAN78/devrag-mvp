# Canvas Execution State & Checkpointing

## Level 1: Conceptual Overview

**Execution State Management** maintains graph execution snapshots, supporting asynchronous execution, job cancellation, human-in-the-loop intermissions (`waiting_for_user`), and checkpoint restoration (`checkpoint_store.go`).

---

## Level 2: Implementation Details

### Source File Map
- **Checkpoint Store**: [checkpoint_store.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/checkpoint_store.go#L1)
- **Interrupt / Resume**: [interrupt_resume.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/interrupt_resume.go#L1)
- **Cancellation**: [cancel.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/cancel.go#L1)

---

### Human-in-the-Loop Interrupt & Resume Lifecycle

```
Node Execution -> Hit Fillup Node (User input required)
   │
   ▼
Emit InterruptSignal -> Yield event `waiting_for_user` (cpn_id)
   │
   ▼
Persist CanvasState to CheckpointStore (Redis / DB)
   │
   ▼  [User submits input form via REST API]
Resume API Called -> Load Checkpoint -> Resume Eino Execution Graph
```

In [interrupt_resume.go](file:///home/logan78/Desktop/ragflow/internal/agent/canvas/interrupt_resume.go#L1):
Interrupt signals carry `__resume_interrupt_id__` and `__resume_data__` payloads. When an execution is resumed, `compose.ResumeWithData` injects human input data directly into the suspended node's input channel.
