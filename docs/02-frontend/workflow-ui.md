# Workflow & Pipeline UI

## Level 1: Dataflow & Pipeline Execution

The Workflow UI provides visual layout elements for defining data pipelines, compilation templates, and task monitoring across data ingestion and pipeline operators.

---

## Level 2: Component Breakdown & Source Links

### Key Subsystems

1. **Compilation Templates Studio** (`/compilation-templates`): Interfaces for selecting, creating, and editing compilation pipeline templates.
   - Source: [`web/src/pages/dataset/compilation/`](file:///home/logan78/Desktop/ragflow/web/src/pages/dataset/compilation)
2. **Dataflow Result Viewer** (`/dataflow-result`): Visualization panels showing stage-by-stage pipeline processing results.
   - Source: [`web/src/pages/dataflow-result/`](file:///home/logan78/Desktop/ragflow/web/src/pages/dataflow-result)
3. **Pipeline Operator Tabs** ([`components/pipeline-operator-tabs`](file:///home/logan78/Desktop/ragflow/web/src/components/pipeline-operator-tabs)): Tab controls for switching between data cleaning, tokenization, embedding, and indexing execution logs.

### Source File Map

- Pipeline Request Hook: [`web/src/hooks/use-pipeline-operator.ts`](file:///home/logan78/Desktop/ragflow/web/src/hooks/use-pipeline-operator.ts)
- Compilation Template Hook: [`web/src/hooks/use-compilation-template-request.ts`](file:///home/logan78/Desktop/ragflow/web/src/hooks/use-compilation-template-request.ts)
- Operator Components: [`web/src/components/pipeline-operator-tabs/`](file:///home/logan78/Desktop/ragflow/web/src/components/pipeline-operator-tabs)
