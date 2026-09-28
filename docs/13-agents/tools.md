# Native Tool Ecosystem & MCP Integration

## Level 1: Conceptual Overview

RAGFlow includes a rich ecosystem of native tools (search engines, financial APIs, translation tools, academic databases) and native support for the Model Context Protocol (MCP). Native tools inherit from `ToolBase`, and MCP integrations dynamically import tool definitions from external MCP servers via stdio or SSE transports.

---

## Level 2: Implementation Details

### Native Tool Catalog

In [agent/tools/](file:///home/logan78/Desktop/ragflow/agent/tools/):

| Tool Module | Source Path | Primary Purpose |
| :--- | :--- | :--- |
| **Retrieval** | [retrieval.py](file:///home/logan78/Desktop/ragflow/agent/tools/retrieval.py#L1) | Knowledge base vector and hybrid chunk retrieval tool |
| **Google** | [google.py](file:///home/logan78/Desktop/ragflow/agent/tools/google.py#L1) | Google Custom Search API integration |
| **DuckDuckGo** | [duckduckgo.py](file:///home/logan78/Desktop/ragflow/agent/tools/duckduckgo.py#L1) | Web search via DuckDuckGo API |
| **Tavily** | [tavily.py](file:///home/logan78/Desktop/ragflow/agent/tools/tavily.py#L1) | AI-focused web search API |
| **ArXiv** | [arxiv.py](file:///home/logan78/Desktop/ragflow/agent/tools/arxiv.py#L1) | Search scientific papers on ArXiv |
| **PubMed** | [pubmed.py](file:///home/logan78/Desktop/ragflow/agent/tools/pubmed.py#L1) | Medical research literature search |
| **DeepL** | [deepl.py](file:///home/logan78/Desktop/ragflow/agent/tools/deepl.py#L1) | Text translation via DeepL API |
| **ExeSQL** | [exesql.py](file:///home/logan78/Desktop/ragflow/agent/tools/exesql.py#L1) | SQL database query execution |
| **QWeather** | [qweather.py](file:///home/logan78/Desktop/ragflow/agent/tools/qweather.py#L1) | Weather forecast and data API |
| **Financial Tools** | `tushare.py`, `akshare.py`, `yahoofinance.py` | Stock market and financial data retrieval |

---

### Model Context Protocol (MCP) Integration

Source paths:
- Python MCP Binding: [common/mcp_tool_call_conn.py](file:///home/logan78/Desktop/ragflow/common/mcp_tool_call_conn.py#L1)
- Go MCP Service: [internal/mcp/connector.go](file:///home/logan78/Desktop/ragflow/internal/mcp/connector.go#L28), [server.go](file:///home/logan78/Desktop/ragflow/internal/mcp/server.go#L1)

MCP tools are translated into standard OpenAI function call schemas via `mcp_tool_metadata_to_openai_tool(mcp_tool)`:

```python
class MCPToolBinding:
    """Binds remote MCP server tools to local Agent component instances."""
    def __init__(self, mcp_server_id, tenant_id): ...
    def get_tools(self) -> list[dict]: ...
    def call_tool(self, tool_name, arguments) -> str: ...
```
