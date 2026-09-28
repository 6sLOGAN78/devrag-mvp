api token auth   • API Token Auth (AUTH_API): Validates the token against standard API keys stored in the APIToken database table to resolve  
  the associated user.
  Read(~/Desktop/ragflow/internal/service/api_token.go) (ctrl+o to expand)
▸ Thought for 6s, 412 tokens
  Prioritizing Specific Tools
  Yes, both the JWT session tokens and the API tokens are generated natively by the Go backend system.                         
                                                                                                                               
  When a user logs in, signs up, or creates an API key, the request is routed to the Go handlers. The Go backend generates     
  these tokens in a specific format that remains completely compatible with the Python backend.                                
                                                                                                                               
  Here's how each token is generated in the Go backend (specifically in internal/utility/token.go and                          
  internal/service/api_token.go):                                                                                              
                                                                                                                               
  ### 1. JWT Session Tokens                                                                                                    
                                                                                                                               
  When a user logs in via the Go endpoint (/api/v1/auth/login), the Go backend constructs the authorization token.             
                                                                                                                               
  • It generates a raw UUID access token (utility.GenerateToken()).                                                            
  • Instead of using a standard JWT format, it explicitly mimics the exact payload structure of Python's itsdangerous.url_safe.
  URLSafeTimedSerializer library.                                                                                              
  • It compresses the token payload using zlib, appends a timestamp, and cryptographically signs it using crypto/hmac and      
  crypto/sha1 in a function called DumpAccessToken.                                                                            
  • This guarantees that the Python backend can still verify and unpack the Go-generated token using its own standard          
  itsdangerous library.                                                                                                        
                                                                                                                               
  ### 2. API Tokens                                                                                                            
                                                                                                                               
  When a user requests a new API key through the Go endpoint (/api/v1/system/tokens POST), the Go backend's CreateAPIKey       
  function handles it directly:                                                                                                
                                                                                                                               
  • Standard API Token (GenerateAPIToken): Generates 32 secure random bytes using Go's crypto/rand package. It then URL-safe   
  base64 encodes the bytes and prepends "ragflow-" to match the format expected by both systems.                               
  • Beta API Token (GenerateBetaAPIToken): Generates a standard UUID, strips out the hyphens, and truncates it to 32 characters.
                                                                                                                               
  By generating these tokens in Go using precise replication of Python's formatting (especially the itsdangerous JWT payloads),
  the system ensures a unified authorization state regardless of whether a request is routed to a Python or Go endpoint.       

────────────────────────────────────────────────────────────
> but llm use api key how to validate if the llm's api key usage is not exhausted by user?

▸ Thought for 6s, 461 tokens
  Prioritizing Specific Tools
● Search(Search balance in Model Service) (ctrl+o to expand)

▸ Thought for 5s, 296 tokens
  Prioritizing Specific Tools

● Search(Search Quota) (ctrl+o to expand)

▸ Thought for 5s, 300 tokens
  Prioritizing Specific Tools
● Search(Search quota) (ctrl+o to expand)

▸ Thought for 5s, 271 tokens
  Prioritizing Specific Tools

● Search(Search exhaust) (ctrl+o to expand)

▸ Thought for 6s, 319 tokens
  Prioritizing Tool Usage
● Search(Search quota in DB) (ctrl+o to expand)

▸ Thought for 4s, 275 tokens
  Prioritizing Tool Usage
● Search(Search balance) (ctrl+o to expand)

▸ Thought for 5s, 301 tokens
  Prioritizing Tool Usage

● Search(Search Provider) (ctrl+o to expand)

▸ Thought for 5s, 289 tokens
  Prioritizing Specific Tools
● Search(Search Tenant class) (ctrl+o to expand)

▸ Thought for 4s, 305 tokens
  Prioritizing Tool Usage
● Search(Search Tenant class line) (ctrl+o to expand)

▸ Thought for 5s, 283 tokens
  Prioritizing Tool Usage
● Read(~/Desktop/ragflow/api/db/db_models.py) (ctrl+o to expand)

▸ Thought for 5s, 309 tokens
  Prioritizing Tool Usage

● Read(~/Desktop/ragflow/api/db/db_models.py) (ctrl+o to expand)

▸ Thought for 6s, 360 tokens
  Prioritizing Tool Usage

● Search(Search Tenant class) (ctrl+o to expand)

▸ Thought for 59s, 275 tokens
  Prioritizing Specific Tools

● Read(~/Desktop/ragflow/api/db/db_models.py) (ctrl+o to expand)

▸ Thought for 48s, 338 tokens
  Prioritizing Specific Tools

● Search(Search used_tokens) (ctrl+o to expand)

▸ Thought for 5s, 291 tokens
  Prioritizing Tool Usage

● Read(~/Desktop/ragflow/api/db/services/tenant_llm_service.py) (ctrl+o to expand)

▸ Thought for 8s, 483 tokens
  Prioritizing Tool Usage

● Search(Search ShowInstanceBalance) (ctrl+o to expand)

▸ Thought for 5s, 277 tokens
  Prioritizing Tool Usage

● Search(Search ShowInstanceBalance) (ctrl+o to expand)

▸ Thought for 5s, 286 tokens
  Prioritizing Tool Usage
● Search(Search ShowInstanceBalance) (ctrl+o to expand)

▸ Thought for 6s, 276 tokens
  Prioritizing Specific Tools
● Read(~/Desktop/ragflow/internal/service/model_service.go) (ctrl+o to expand)

▸ Thought for 5s, 270 tokens
  Prioritizing Specific Tools

● Read(~/Desktop/ragflow/internal/service/model_service.go) (ctrl+o to expand)

▸ Thought for 7s, 453 tokens
  Prioritizing Tool Usage

● Search(Search max_tokens) (ctrl+o to expand)

▸ Thought for 7s, 437 tokens
  Prioritizing Tool Usage

● Search(Search used_tokens in Go) (ctrl+o to expand)

▸ Thought for 6s, 382 tokens
  Prioritizing Tool Usage
● Search(Search credit in Python) (ctrl+o to expand)

▸ Thought for 5s, 310 tokens
  Prioritizing Specific Tools
● Search(Search decrease_credit) (ctrl+o to expand)

▸ Thought for 5s, 280 tokens
  Prioritizing Tool Usage

● Search(Search def user_service) (ctrl+o to expand)
▸ Thought for 5s, 282 tokens
  Prioritizing Tool Usage
● Search(Search decrease) (ctrl+o to expand)

▸ Thought for 5s, 276 tokens
  Prioritizing Tool Usage

● Search(Search TenantService.decrease) (ctrl+o to expand)

▸ Thought for 7s, 582 tokens
  Prioritizing Tool Usage

● Search(Search insufficient_quota) (ctrl+o to expand)

▸ Thought for 7s, 474 tokens
  Prioritizing Tool Usage

● Search(Search Balance) (ctrl+o to expand)

▸ Thought for 5s, 293 tokens
  Prioritizing Tool Usage

● Search(Search modelModule import) (ctrl+o to expand)

▸ Thought for 7s
  Prioritizing Specific Tools
  To validate whether an LLM's API key usage has been exhausted, RAGFlow relies on a combination of direct balance querying and
  external provider enforcement, rather than enforcing hard local token caps.                                                  
                                                                                                                               
  Here is how the validation works:                                                                                            
                                                                                                                               
  ### 1. Direct Balance Check via Provider APIs                                                                                
                                                                                                                               
  RAGFlow provides a specific endpoint (GET /api/v1/providers/{provider_name}/instances/{instance_name}/balance) that checks   
  the remaining quota of an API key.                                                                                           
  In the Go backend (internal/service/model_service.go), the ShowInstanceBalance method retrieves the user's API key from the  
  database and invokes the Balance(ctx, apiConfig) function of the specific model driver (e.g., OpenAI, DeepSeek, Anthropic).  
  This makes an HTTP request to the LLM provider's billing or dashboard API to retrieve the actual remaining monetary balance  
  or token quota on that key.                                                                                                  
                                                                                                                               
  ### 2. Runtime Exhaustion (Provider Enforcement)                                                                             
                                                                                                                               
  During actual LLM inferences (chat, embeddings, OCR, etc.), RAGFlow does not proactively block requests by checking a local  
  quota threshold beforehand. Instead:                                                                                         
                                                                                                                               
  • It sends the request to the LLM provider.                                                                                  
  • If the API key is out of credits or has hit its rate limit, the external provider returns an HTTP error (such as 429 Too   
  Many Requests or 402 Payment Required with an insufficient_quota message).                                                   
  • RAGFlow catches this exception and propagates the error message back to the frontend/user.                                 
                                                                                                                               
  ### 3. Local Analytics Tracking (used_tokens)                                                                                
                                                                                                                               
  While it relies on the provider for hard validation, RAGFlow still tracks usage locally for metrics. As requests complete    
  successfully, the backend calls increase_usage methods (e.g., TenantLLMService.increase_usage in the Python backend) to      
  increment the used_tokens column in the TenantLLM / TenantModel database tables. This provides visibility into how many      
  tokens a specific tenant or instance has consumed across the application, but it does not act as a hard kill-switch.         

────────────────────────────────────────────────────────────
> what is api token is used for ?### 2. API Tokens
  
    When a user requests a new API key through the Go endpoint (/api/v1/system/tokens POST), the Go backend's CreateAPIKey
    function handles it directly:
  
    • Standard API Token (GenerateAPIToken): Generates 32 secure random bytes using Go's crypto/rand package. It then URL-safe
    base64 encodes the bytes and prepends "ragflow-" to match the format expected by both systems.
    • Beta API Token (GenerateBetaAPIToken): Generates a standard UUID, strips out the hyphens, and truncates it to 32
  characters.
  
    By generating these tokens in Go using precise replication of Python's formatting (especially the itsdangerous JWT payloads),
    the system ensures a unified authorization state regardless of whether a request is routed to a Python or Go endpoint. this

▸ Thought for 8s, 516 tokens
  Prioritizing Tool Usage

● Search(Search AUTH_BETA) (ctrl+o to expand)

▸ Thought for 5s, 313 tokens
  Prioritizing Specific Tools

● Search(Search DialogID in api_token) (ctrl+o to expand)

▸ Thought for 9s, 711 tokens
  Prioritizing Specific Tools
  In RAGFlow, the two types of API tokens serve different security scopes and use cases. They allow users and external         
  applications to interact with the system programmatically without needing a browser-based session (which uses the JWT).      
  
  Here is what each token is used for:
  
  ### 1. Standard API Token
  
  Purpose: Full programmatic access to RAGFlow's core APIs.
  
  • Scope: Broad access. It acts as a direct substitute for a user's logged-in session. When you authenticate with this token, 
  you have permission to do anything the tenant/user can do.
  • Use Cases:
      • Using the RAGFlow Python/Go SDKs to automate workflows.
      • Creating and managing datasets, uploading documents, or triggering ingestion pipelines via scripts.
      • Integrating RAGFlow's backend management features directly into another internal application.
  • Technical Mapping: It is accepted on almost all standard endpoints (via AUTH_API in Python or AuthMiddleware in Go).       
  
  ### 2. Beta API Token
  
  Purpose: Scoped, restricted access specifically for public-facing bots and agents.
  
  • Scope: Narrow access. This token is often tied to a specific chatbot, search bot, or agent (linked via a dialog_id). It    
  intentionally does not grant access to the user's workspace, datasets, or backend configurations.
  • Use Cases:
      • Embedding a customer service chatbot into a public website. You use the Beta token so the widget can send messages and 
      receive completions without exposing your entire RAGFlow account.
      • Providing access to specific Agent endpoints or Search endpoints.
      • Exposing RAGFlow capabilities as tools via the Model Context Protocol (MCP) endpoints. 
  • Technical Mapping: It is only accepted on a restricted subset of endpoints (like /api/v1/chatbots, /api/v1/agentbots, and
  /api/v1/mcp) via the AUTH_BETA auth type in Python or the BetaAuthMiddleware() in Go.