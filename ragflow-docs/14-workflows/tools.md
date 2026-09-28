# Workflow Tool Nodes & Extension Plugins

## Level 1: Conceptual Overview

**Workflow Tools** allow canvas components to interact with external APIs, databases, scrapers, and custom plugin modules (`agent/plugin/*`). Tools receive input variables from upstream canvas nodes and emit output dictionaries back into the workflow state context.

---

## Level 2: Implementation Details

### Source File Map
- **Plugin Manager**: [plugin_manager.py](file:///home/logan78/Desktop/ragflow/agent/plugin/plugin_manager.py#L1)
- **Embedded Plugins**: [agent/plugin/embedded_plugins/](file:///home/logan78/Desktop/ragflow/agent/plugin/embedded_plugins/)
- **Invoke Component**: [invoke.py](file:///home/logan78/Desktop/ragflow/agent/component/invoke.py#L57)
- **Browser Component**: [browser.py](file:///home/logan78/Desktop/ragflow/agent/component/browser.py#L83)

---

### Plugin Extension Architecture

In [plugin_manager.py](file:///home/logan78/Desktop/ragflow/agent/plugin/plugin_manager.py#L1):

Custom workflow tools are dynamically discovered and instantiated via the `PluginManager`:

```python
class PluginManager:
    """Discovers, validates, and loads user-defined tool plugins."""
    def load_plugins(self): ...
    def get_plugin(self, name): ...
```

Tools implement standard `ans(params)` signatures:
```python
def ans(self, params: dict) -> dict:
    """Executes tool logic and returns structured output dict."""
    # Perform HTTP request / calculation / database operation
    return {"result": data, "status": "success"}
```
