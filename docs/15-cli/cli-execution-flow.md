# CLI Execution Flow

## Level 1: Conceptual Explanation

The CLI execution flow transforms raw text typed into the terminal into executed REST API requests or Virtual Filesystem operations. The lifecycle consists of:
1. **Lexical Analysis (Tokenizer)**: Converts character streams into structured tokens ([`internal/cli/lexer.go`](file:///home/logan78/Desktop/ragflow/internal/cli/lexer.go)).
2. **Syntactic Analysis (Parser)**: Validates command grammar via recursive descent parsing and builds a `Command` AST struct ([`internal/cli/parser.go`](file:///home/logan78/Desktop/ragflow/internal/cli/parser.go)).
3. **Execution Dispatch**: Maps command types to REST HTTP handlers or VFS providers ([`internal/cli/cli.go`](file:///home/logan78/Desktop/ragflow/internal/cli/cli.go)).
4. **HTTP Transport**: Constructs JSON HTTP payloads, adds Bearer/API Key headers, dispatches over TCP, and handles timeouts ([`internal/cli/http_client.go`](file:///home/logan78/Desktop/ragflow/internal/cli/http_client.go)).
5. **Response Formatting**: Renders responses into ASCII tables, plain text, or raw JSON ([`internal/cli/response.go`](file:///home/logan78/Desktop/ragflow/internal/cli/response.go)).

---

## Level 2: Implementation Details

### Step 1: Lexical Analysis (`Lexer`)
Defined in [`internal/cli/lexer.go#L25-L80`](file:///home/logan78/Desktop/ragflow/internal/cli/lexer.go#L25-L80):
- Scans input character by character using `readChar()`.
- Identifies single-character tokens (`;`, `,`, `/`, `-`, `[`, `]`), identifiers, numbers, and quoted strings (`'...'` or `"..."`).
- Skips whitespace and handles escape sequences (`\'`, `\"`).

### Step 2: Parsing (`Parser`)
Defined in [`internal/cli/parser.go#L27-L60`](file:///home/logan78/Desktop/ragflow/internal/cli/parser.go#L27-L60):
- Uses lookahead tokens (`curToken` and `peekToken`).
- Routes parsing based on token types (`TokenLogin`, `TokenList`, `TokenCreate`, `TokenSearch`, etc.) into specific parser methods in [`user_parser.go`](file:///home/logan78/Desktop/ragflow/internal/cli/user_parser.go) or [`admin_parser.go`](file:///home/logan78/Desktop/ragflow/internal/cli/admin_parser.go).
- Returns a structured `Command` struct:
  ```go
  type Command struct {
      Type   string
      Params map[string]interface{}
  }
  ```

### Step 3: Execution & HTTP Dispatch
Defined in [`internal/cli/user_command.go#L60-L150`](file:///home/logan78/Desktop/ragflow/internal/cli/user_command.go#L60-L150) and [`internal/cli/http_client.go#L30-L100`](file:///home/logan78/Desktop/ragflow/internal/cli/http_client.go#L30-L100):
- Extracts parameters from `Command.Params`.
- Constructs endpoint URL, e.g., `http://127.0.0.1:9384/v1/dataset/list`.
- Injects HTTP Headers:
  - `Content-Type: application/json`
  - `Authorization: Bearer <jwt_token>` or `Authorization: <api_key>`
- Dispatches request via Go `net/http` client with connection pooling.

### Step 4: Formatting & Output
Defined in [`internal/cli/response.go#L45-L120`](file:///home/logan78/Desktop/ragflow/internal/cli/response.go#L45-L120) and [`internal/cli/table.go#L20-L100`](file:///home/logan78/Desktop/ragflow/internal/cli/table.go#L20-L100):
- Parses HTTP response JSON.
- Evaluates `OutputFormatTable`, `OutputFormatPlain`, or `OutputFormatJSON`.
- `OutputFormatTable` dynamically calculates column widths, prints header borders, and outputs formatted tabular text to `os.Stdout`.

---

## Execution Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as User / REPL
    participant Shell as CLI Shell (cli.go)
    participant Lexer as Lexer (lexer.go)
    participant Parser as Parser (parser.go / user_parser.go)
    participant Dispatch as Command Router (user_command.go)
    participant HTTP as RAGFlowHTTPClient (http_client.go)
    participant Server as RAGFlow API Server
    participant Render as Table Formatter (response.go / table.go)

    User->>Shell: Types "SEARCH 'vector db' ON DATASETS 'kb1';"
    Shell->>Parser: NewParser(input).Parse(APIMode)
    Parser->>Lexer: NextToken()
    Lexer-->>Parser: TokenSearch, TokenQuotedString('vector db'), etc.
    Parser-->>Shell: Command{Type: "api_search", Params: map[...]}
    Shell->>Dispatch: ExecuteUserCommand(cmd)
    Dispatch->>HTTP: PostJSON("/v1/api/retrieval", payload)
    HTTP->>Server: HTTP POST /v1/api/retrieval (Auth Header)
    Server-->>HTTP: HTTP 200 OK {code: 0, data: {chunks: [...]}}
    HTTP-->>Dispatch: Returns JSON response
    Dispatch->>Render: FormatSearchResponse(json, OutputFormatTable)
    Render-->>Shell: Formatted ASCII grid string
    Shell-->>User: Prints ASCII result table
```

---

## References & Source Links

- [`internal/cli/lexer.go:L25-L100`](file:///home/logan78/Desktop/ragflow/internal/cli/lexer.go#L25-L100) - Tokenizer implementation.
- [`internal/cli/parser.go:L27-L120`](file:///home/logan78/Desktop/ragflow/internal/cli/parser.go#L27-L120) - Recursive descent parser engine.
- [`internal/cli/http_client.go:L30-L120`](file:///home/logan78/Desktop/ragflow/internal/cli/http_client.go#L30-L120) - HTTP network client wrapper.
- [`internal/cli/response.go:L45-L150`](file:///home/logan78/Desktop/ragflow/internal/cli/response.go#L45-L150) - Output rendering logic.
- [`internal/cli/table.go:L20-L100`](file:///home/logan78/Desktop/ragflow/internal/cli/table.go#L20-L100) - Grid table drawing logic.
