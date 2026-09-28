# Search Engine Integrations & Web Retrieval

## Level 1: Conceptual Overview

**Search Integrations** enable RAGFlow assistants and agents to query live external web search APIs (Google, DuckDuckGo, Tavily, SearxNG, Querit, Bing) and academic databases (ArXiv, PubMed, Google Scholar) when local knowledge bases do not contain adequate answers.

---

## Level 2: Implementation Details

### Source File Map
- **Google Search**: [agent/tools/google.py](file:///home/logan78/Desktop/ragflow/agent/tools/google.py#L1)
- **DuckDuckGo**: [agent/tools/duckduckgo.py](file:///home/logan78/Desktop/ragflow/agent/tools/duckduckgo.py#L1)
- **Tavily Search**: [agent/tools/tavily.py](file:///home/logan78/Desktop/ragflow/agent/tools/tavily.py#L1)
- **SearxNG**: [agent/tools/searxng.py](file:///home/logan78/Desktop/ragflow/agent/tools/searxng.py#L1)
- **ArXiv & PubMed**: [agent/tools/arxiv.py](file:///home/logan78/Desktop/ragflow/agent/tools/arxiv.py#L1), [agent/tools/pubmed.py](file:///home/logan78/Desktop/ragflow/agent/tools/pubmed.py#L1)

---

### Web Search Fallback Mechanism

In [dialog_service.py](file:///home/logan78/Desktop/ragflow/api/db/services/dialog_service.py#L584-L590):
If a dialog has web search enabled (`use_web_search = True`), the retrieval engine queries configured web search providers to extract real-time web page snippets, merging them into context prompts alongside local document chunks.
