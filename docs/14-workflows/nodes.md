# Canvas Node Types & Component Specifications

## Level 1: Conceptual Overview

Canvas nodes represent individual processing steps in a workflow DAG. RAGFlow includes 20+ built-in node component types covering input processing, LLM generation, knowledge retrieval, flow control, variable manipulation, document generation, and browser automation.

---

## Level 2: Implementation Details

### Comprehensive Node Catalog

In [agent/component/](file:///home/logan78/Desktop/ragflow/agent/component/) & [internal/agent/component/](file:///home/logan78/Desktop/ragflow/internal/agent/component/):

| Node Type | Implementation File | Purpose & Parameters |
| :--- | :--- | :--- |
| **Begin** | [begin.py](file:///home/logan78/Desktop/ragflow/agent/component/begin.py#L36) | Workflow entry point; defines input fields (`sys.query`, `sys.files`) |
| **Generate (LLM)** | [llm.py](file:///home/logan78/Desktop/ragflow/agent/component/llm.py#L90) | Invokes LLM chat driver with prompt template & generation parameters |
| **Retrieval** | [retrieval.py](file:///home/logan78/Desktop/ragflow/agent/tools/retrieval.py#L1) | Searches Knowledge Bases (`kb_ids`) via hybrid vector/keyword retrieval |
| **Categorize** | [categorize.py](file:///home/logan78/Desktop/ragflow/agent/component/categorize.py#L90) | Classifies input into pre-defined categories using LLM reasoning |
| **Switch** | [switch.py](file:///home/logan78/Desktop/ragflow/agent/component/switch.py#L56) | Conditional logical branching based on variable comparison expressions |
| **AgentWithTools** | [agent_with_tools.py](file:///home/logan78/Desktop/ragflow/agent/component/agent_with_tools.py#L74) | Autonomous ReAct agent executing tools & MCP servers |
| **Message** | [message.py](file:///home/logan78/Desktop/ragflow/agent/component/message.py#L65) | Streams reply messages directly to client chat window |
| **Loop** | [loop.py](file:///home/logan78/Desktop/ragflow/agent/component/loop.py#L38) | Executes an inner subgraph until termination condition is met |
| **Iteration** | [iteration.py](file:///home/logan78/Desktop/ragflow/agent/component/iteration.py#L45) | Iterates over items in an array variable |
| **ExitLoop** | [exit_loop.py](file:///home/logan78/Desktop/ragflow/agent/component/exit_loop.py#L25) | Breaks execution out of an active `Loop` subgraph |
| **VariableAggregator** | [variable_aggregator.py](file:///home/logan78/Desktop/ragflow/agent/component/variable_aggregator.py#L54) | Merges variables from multiple branches into a single output |
| **VariableAssigner** | [variable_assigner.py](file:///home/logan78/Desktop/ragflow/agent/component/variable_assigner.py#L39) | Sets or updates global workflow variables |
| **ListOperations** | [list_operations.py](file:///home/logan78/Desktop/ragflow/agent/component/list_operations.py#L48) | Performs list filtering, sorting, indexing, and concatenation |
| **DataOperations** | [data_operations.py](file:///home/logan78/Desktop/ragflow/agent/component/data_operations.py#L43) | Operates on JSON/dict data structures |
| **StringTransform** | [string_transform.py](file:///home/logan78/Desktop/ragflow/agent/component/string_transform.py#L47) | Regex substitution, string split/join, and formatting |
| **ExcelProcessor** | [excel_processor.py](file:///home/logan78/Desktop/ragflow/agent/component/excel_processor.py#L71) | Parses and transforms Excel (.xlsx) spreadsheets |
| **DocsGenerator** | [docs_generator.py](file:///home/logan78/Desktop/ragflow/agent/component/docs_generator.py#L75) | Renders Word/PDF document reports from templates |
| **Fillup** | [fillup.py](file:///home/logan78/Desktop/ragflow/agent/component/fillup.py#L35) | Human-in-the-loop input form component |
| **Invoke** | [invoke.py](file:///home/logan78/Desktop/ragflow/agent/component/invoke.py#L57) | Makes external HTTP REST web API requests |
| **Browser** | [browser.py](file:///home/logan78/Desktop/ragflow/agent/component/browser.py#L83) | Automated headless browser web scraping component |
