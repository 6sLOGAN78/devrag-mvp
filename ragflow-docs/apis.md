# RAGFlow API Endpoint Catalog

  

This document outlines the exact routing and division of labor between the Go API Gateway and the Python ASGI Server based on the RAGFlow system architecture.

  

## How Routing Works in Practice

In front of these services, Nginx (or the Go Gin gateway reverse proxy) routes incoming URLs:

- Calls matching `/api/v1/auth/*`, `/v1/user/*`, `/v1/tenant/*`, and `/api/v1/mcp` route directly to **Go (port 9380)**.

- Calls matching `/api/v1/datasets/*`, `/api/v1/agents/*`, and `/api/v1/chat/*` route to **Python (port 9381 / ASGI server)**.

  

---

  

## 1. Endpoints Handled by the Go Backend

*(Focus: Auth, Identity, High-Concurrency Gateway, and MCP)*

  

### Authentication & User Management

* `POST /api/v1/auth/login` — User login via email & password (issues JWT).

* `POST /api/v1/users` — User registration.

* `POST /api/v1/auth/password/forgot/otp` — Send OTP for password reset.

* `POST /api/v1/auth/password/reset` — Reset password using OTP.

* `GET /v1/user/info` — Fetch current user profile, avatar, and roles.

* `POST /v1/user/setting` — Update user profile settings.

* `POST /v1/user/setting/password` — Change password.

  

### Tenant & Workspace Management

* `GET /v1/user/tenant_info` — Retrieve tenant/workspace settings and plan details.

* `GET /v1/tenant/list` — List accessible tenant workspaces for the current user.

  

### System & Health Checks

* `GET /health` — Basic service health check.

* `GET /api/v1/system/ping` — Server ping check.

* `GET /api/v1/system/config` — Public system configuration parameters.

* `GET /api/v1/system/version` — RAGFlow version string.

* `GET /api/v1/language` — Runtime language detection (go vs python).

  

### Search Bots & MCP (Model Context Protocol)

* `POST /api/v1/searchbots/ask` — High-concurrency search bot question answering.

* `POST /api/v1/searchbots/retrieval_test` — Fast retrieval accuracy test against knowledge bases.

* `POST /api/v1/mcp` — JSON-RPC endpoint for Model Context Protocol integrations.

  

---

  

## 2. Endpoints Handled by the Python Backend

*(Focus: AI Workflows, Ingestion Triggering, Search, Real-Time Streaming, and core CRUD for AI entities)*

  

### Knowledge Base (Datasets) & Document Management

* `GET /api/v1/datasets` — List knowledge bases.

* `POST /api/v1/datasets` — Create a new knowledge base (dataset).

* `PUT /api/v1/datasets/<dataset_id>` — Update dataset settings (parser mode, embedding model).

* `DELETE /api/v1/datasets` — Delete a dataset and its vector index.

* `GET /api/v1/datasets/<dataset_id>/documents` — List documents inside a dataset.

* `POST /api/v1/documents/upload` — Upload raw files (.pdf, .docx, etc.). *(Note: Go also proxies/streams this to MinIO)*.

* `POST /api/v1/datasets/<dataset_id>/documents/parse` — Trigger DeepDoc parsing & chunking tasks for documents.

* `POST /api/v1/datasets/<dataset_id>/documents/batch-update-status` — Enable/disable document chunks from search.

* `DELETE /api/v1/datasets/<dataset_id>/documents` — Delete document and prune its vector chunks.

* `GET /api/v1/datasets/<dataset_id>/documents/<doc_id>/chunks` — Retrieve text chunks and visual bounding boxes.

* `POST /api/v1/datasets/<dataset_id>/documents/<doc_id>/chunks` — Manually create or edit a chunk.

  

### Agent & Visual Canvas Workflows

* `GET /api/v1/agents` — List available agent workflows.

* `POST /api/v1/agents` — Create an agent workflow canvas graph.

* `GET /api/v1/agents/<agent_id>` — Get canvas node topology (React Flow JSON/DSL).

* `DELETE /api/v1/agents/<agent_id>` — Delete an agent workflow.

* `POST /api/v1/agents/chat/completions` — Execute agent DAG graph with token-by-token streaming.

  

### Chat Dialogue & Streaming

* `GET /api/v1/chats` — List configured chat assistants.

* `POST /api/v1/chats` — Create a chat assistant linked to datasets.

* `DELETE /api/v1/chats/<chat_id>` — Delete a chat assistant.

* `GET /api/v1/chats/<chat_id>/sessions` — List dialogue conversation sessions.

* `POST /api/v1/chat/completions` — Stream RAG chat completion via Server-Sent Events (SSE).
* how to design production level api key system lke my app generated api key and user use them to get api calls in my backedn or system and they pay let's say they paid 5 dollards and get some amount of call and how it is done like database redis and what alternatives compete guide

Yes. What you're describing is essentially a **metered API platform**:

> User signs up → creates API key → pays $5 → receives credits/quota → sends requests with key → your system authenticates key → checks quota/rate limit → executes request → records usage → deducts credits → blocks when exhausted.

This is how many API businesses are architected. AWS API Gateway, for example, has the concepts of API keys, usage plans, throttling and quotas; Kong similarly has consumers, key authentication and rate limiting.

The important thing is: **don't think of this as just an API-key table + Redis counter.** You need several separate systems.

---

# 1. The production architecture

A good architecture looks like this:

```
                         ┌──────────────────────┐
                         │      Dashboard       │
                         │                      │
                         │ Create API Key       │
                         │ Buy Credits          │
                         │ View Usage           │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     Your Backend     │
                         │                      │
                         │ Auth / Billing APIs  │
                         └──────────┬───────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
          PostgreSQL             Stripe              Redis
          ──────────             ──────              ─────
          Users                  Payments             Rate limits
          API keys               Webhooks             Hot counters
          Plans                  Invoices              Quotas
          Credits                Subscriptions         Locks
          Usage ledger
                │
                │
                ▼
       ┌─────────────────────┐
       │     API Gateway      │
       │                     │
       │ API Key validation  │
       │ Rate limiting       │
       │ Request routing     │
       └──────────┬──────────┘
                  │
                  ▼
          ┌───────────────┐
          │ Your API      │
          │ /v1/chat      │
          │ /v1/search    │
          │ /v1/generate  │
          └───────┬───────┘
                  │
                  ▼
             Usage Event
                  │
                  ▼
          ┌───────────────┐
          │ Usage Worker  │
          │               │
          │ meter usage   │
          │ write ledger  │
          │ analytics     │
          └───────┬───────┘
                  │
                  ▼
             PostgreSQL
```

There are **four different concerns** here:

1. **Authentication** — Is this API key legitimate?
2. **Authorization** — What is this key allowed to access?
3. **Rate limiting** — Can it make requests this quickly?
4. **Billing/metering** — Has this customer paid / how much usage remains?

Don't combine these.

---

# 2. First: understand API keys

Suppose your customer creates:

```
sk_live_7Hk92jL...something...
```

They call:

```
POST /v1/generate

Authorization: Bearer sk_live_7Hk92jL...
```

or:

```
X-API-Key: sk_live_7Hk92jL...
```

Your backend needs to determine:

```
key
 ↓
who owns it?
 ↓
is it active?
 ↓
what plan?
 ↓
what permissions?
 ↓
how many credits?
 ↓
rate limit?
 ↓
allow/reject
```

---

# 3. NEVER store the actual API key

This is extremely important.

Don't do:

```
api_keys

id
user_id
key = "sk_live_7Hk92j..."
```

Instead generate:

```
sk_live_7Hk92jL8xK...
```

and store a hash:

```
api_keys

id
user_id
key_hash
key_prefix
status
created_at
last_used_at
expires_at
```

For example:

```
actual key:

sk_live_7Hk92jL8xK9abc...

stored:

key_prefix = sk_live_7Hk9
key_hash   = SHA256(actual_key)
```

When the request comes:

```
incoming key
      │
      ▼
SHA256(key)
      │
      ▼
database / cache lookup
      │
      ▼
key_hash
```

You only show the complete secret **once** when the customer creates it.

This is similar to the general approach used by production API platforms: the key itself is a credential, while the platform associates it with a consumer/customer. Kong, for example, associates generated keys with Consumers.

---

# 4. Your database model

I'd start with PostgreSQL.

Something approximately like:

```
users
─────
id
email
created_at


organizations
─────────────
id
name
created_at


api_keys
────────
id
organization_id
name
key_hash
key_prefix
status
created_at
expires_at
last_used_at


plans
─────
id
name
price
credits
requests_per_second
requests_per_month


subscriptions
────────────
id
organization_id
plan_id
stripe_customer_id
stripe_subscription_id
status
current_period_start
current_period_end


credit_accounts
───────────────
id
organization_id
balance
version
updated_at


credit_ledger
─────────────
id
organization_id
api_key_id
type
amount
reference_id
created_at


usage_events
────────────
id
organization_id
api_key_id
endpoint
request_id
units
cost
created_at
```

The **ledger** is particularly important.

---

# 5. Don't just maintain `credits = 938`

A beginner might do:

```
users
-----
credits = 938
```

and decrement:

```
UPDATE users
SET credits = credits - 1
WHERE id = ?;
```

This becomes painful when you have:

- refunds
- failed requests
- duplicate requests
- race conditions
- multiple API servers
- different endpoint prices
- billing disputes
- refunds
- chargebacks
- manual credits
- promotional credits

Instead use a ledger.

Example:

```
credit_ledger

+1000  purchase
-1     api_call
-1     api_call
-5     expensive_endpoint
+100   promotional_credit
```

Then you can reconstruct exactly what happened.

---

# 6. $5 → credits

Suppose you sell:

```
$5 → 10,000 credits
```

Don't necessarily call them "API calls."

Because later you might have:

```
GET /users       = 1 credit
POST /search     = 5 credits
POST /generate   = 20 credits
POST /premium    = 100 credits
```

Or for AI:

```
input token      = $X
output token     = $Y
image generation = $Z
```

So define a **metering unit**.

For example:

```
1 credit = $0.0005

$5 = 10,000 credits
```

Then:

```
endpoint              cost

/v1/search             5 credits
/v1/generate           20 credits
/v1/embedding          2 credits
```

This gives you much more flexibility.

---

# 7. Redis and PostgreSQL have different jobs

This is probably the most important architectural distinction.

### PostgreSQL

Use PostgreSQL for:

```
Users
API keys
Plans
Subscriptions
Credit ledger
Permanent usage records
Invoices
Payment information
```

Postgres is your **source of truth**.

---

### Redis

Use Redis for:

```
Rate limits
Short-lived counters
API key cache
Distributed locks
Temporary usage aggregation
Idempotency
```

Redis should generally **not be the authoritative billing ledger**.

Think:

```
Postgres = bank

Redis = cash register / traffic cop
```

You don't want your customer's $5 balance to disappear because Redis restarted.

---

# 8. Rate limiting is different from quota

Suppose the customer bought:

```
10,000 credits
```

That's their **quota**.

But you might also give them:

```
10 requests/sec
100 requests/min
```

That's their **rate limit**.

These are different.

Example:

```
Customer:

Credits:
10,000

Rate:
10 req/sec

Daily:
5,000 requests
```

A customer could have:

```
9999 credits
```

but still get:

```
429 Too Many Requests
```

because they're sending requests too quickly.

AWS explicitly separates throttling/rate limits from quotas in its API Gateway usage plans.

---

# 9. Redis rate limiter

For example:

```
rate_limit:{organization_id}:second
```

or:

```
rate_limit:{api_key_id}:second
```

Request:

```
API request
     │
     ▼
Redis INCR
     │
     ├── count <= 10
     │       ↓
     │      allow
     │
     └── count > 10
             ↓
           429
```

You can use:

- Fixed window
- Sliding window
- Token bucket
- Leaky bucket

For a serious production system, **token bucket** or sliding-window approaches are usually preferable to a naive fixed counter.

Kong's rate-limiting system, for example, supports multiple rate-limit approaches and Redis-backed advanced rate limiting.

---

# 10. The REALLY important part: concurrent requests

Imagine the customer has:

```
remaining = 1 credit
```

Then 20 requests arrive simultaneously:

```
Request A ──┐
Request B ──┤
Request C ──┤
Request D ──┤
...         ├──> your servers
Request T ──┘
```

If every server does:

```
read balance
if balance > 0:
    process
    decrement
```

you can accidentally allow:

```
20 requests
```

with only:

```
1 credit
```

remaining.

This is a **race condition**.

---

# 11. Atomic credit deduction

You need an atomic operation.

For example PostgreSQL:

```
UPDATE credit_accounts
SET balance = balance - 1
WHERE organization_id = $1
AND balance >= 1
RETURNING balance;
```

If a row is returned:

```
allowed
```

If no row:

```
insufficient credits
```

This is much safer than:

```
SELECT balance
UPDATE balance
```

as two independent operations.

You can also implement this using transactions / row locks depending on your model.

---

# 12. But don't necessarily deduct synchronously for everything

There's an important production optimization.

Suppose your API receives:

```
100,000 requests/sec
```

You don't necessarily want every request doing a PostgreSQL transaction.

Instead:

```
                     ┌───────────┐
request ────────────>│   Redis   │
                     │ fast meter│
                     └─────┬─────┘
                           │
                           ▼
                     usage events
                           │
                           ▼
                         Kafka
                           │
                           ▼
                    usage workers
                           │
                           ▼
                       Postgres
```

Redis handles the fast path.

Kafka / queue handles durable event processing.

Postgres stores the final accounting.

But **the exact design depends heavily on whether "credits" must be hard-enforced with zero overspend or whether small reconciliation windows are acceptable.**

---

# 13. A very good production request flow

I'd design your API request pipeline roughly like this:

```
Client
  │
  │ Authorization: Bearer sk_live_...
  ▼
Load Balancer
  │
  ▼
API Gateway
  │
  ├── TLS
  ├── IP protection
  ├── request size limits
  └── basic DDoS protection
  │
  ▼
Authentication middleware
  │
  ▼
Hash API key
  │
  ▼
Redis
  │
  ├── key cached?
  │       │
  │       └── yes → identity
  │
  └── no
        │
        ▼
     Postgres
        │
        ▼
     cache key
  │
  ▼
Authorization
  │
  ├── key active?
  ├── endpoint allowed?
  └── organization active?
  │
  ▼
Rate limiter
  │
  ├── allowed
  └── 429
  │
  ▼
Quota / credit check
  │
  ├── sufficient
  └── 402/429 depending on your API semantics
  │
  ▼
Your actual business logic
  │
  ▼
Usage event
  │
  ├── request_id
  ├── organization
  ├── API key
  ├── endpoint
  ├── units
  └── cost
  │
  ▼
Response
```

---

# 14. Payment flow

For payments, don't build payment processing yourself.

Use something like:

Stripe

The flow becomes:

```
Customer
   │
   ▼
Your dashboard
   │
   ▼
Stripe Checkout
   │
   ▼
Payment succeeds
   │
   ▼
Stripe webhook
   │
   ▼
Your backend
   │
   ▼
Verify webhook
   │
   ▼
Add credits
   │
   ▼
credit_ledger
```

The critical point:

**Don't give credits because the frontend says payment succeeded.**

The server should process the payment provider's verified webhook.

For recurring/subscription products, Stripe's usage/billing infrastructure can also be used rather than implementing every billing mechanism yourself.

---

# 15. Example: customer buys $5

Let's make the entire thing concrete.

You have:

```
Plan: Starter

Price: $5
Credits: 10,000

Rate:
10 req/sec

Monthly:
10,000 credits
```

Customer pays:

```
$5
```

Stripe sends:

```
payment_succeeded
```

Your backend transaction:

```
subscription
     │
     ▼
credit_ledger

+10,000 PURCHASE
```

Their balance:

```
10,000
```

Then:

```
POST /v1/search
Authorization: Bearer sk_live_abc...
```

Your API determines:

```
cost = 5 credits
```

Then:

```
10,000
   ↓
9,995
```

Ledger:

```
+10,000 purchase
-5      /v1/search
```

Then another:

```
POST /v1/search
```

becomes:

```
9,990
```

---

# 16. What happens at zero?

Eventually:

```
balance = 0
```

Request:

```
POST /v1/search
```

Your authorization/metering layer says:

```
INSUFFICIENT_CREDITS
```

Response could be:

```
402 Payment Required
```

with:

```
{
  "error": {
    "code": "insufficient_credits",
    "message": "Your account has insufficient credits."
  }
}
```

Then the customer goes:

```
Dashboard
    ↓
Buy credits
    ↓
Stripe
    ↓
Webhook
    ↓
+10,000 credits
```

and they're back in business.

---

# 17. API key vs customer vs organization

Don't make this:

```
user → API key
```

only.

A production system should usually be:

```
User
 │
 └── Organization
       │
       ├── API Key A
       ├── API Key B
       ├── API Key C
       │
       ├── Subscription
       │
       └── Credit Account
```

Why?

Because a company might have:

```
Production key
Development key
Staging key
CI/CD key
Mobile key
```

and you want to revoke one without affecting the others.

---

# 18. API key scopes

Give keys permissions.

Example:

```
key_1

permissions:
    search:read
    search:write
```

Another:

```
key_2

permissions:
    embeddings:create
```

Then:

```
API request
     │
     ▼
API key
     │
     ▼
permissions
     │
     ▼
endpoint
```

This becomes very useful later.

---

# 19. Key lifecycle

Your API keys should have states:

```
ACTIVE
REVOKED
EXPIRED
```

For example:

```
sk_live_abc
   │
   ├── active
   │
   ├── revoked
   │
   └── expired
```

Your dashboard should have:

```
API Keys

Production
sk_live_************9X2
Created: Aug 12
Last used: 2 min ago
Status: Active

[Revoke]
```

And:

```
Create new key
```

---

# 20. Key rotation

Production systems should support:

```
Old key
   +
New key
```

simultaneously.

For example:

```
Day 1

key_A → active


Day 2

key_A → active
key_B → active


Day 7

key_A → revoked
key_B → active
```

This lets customers rotate credentials without downtime.

---

# 21. Idempotency

This becomes **very important for paid APIs**.

Suppose:

```
POST /v1/generate
```

costs:

```
20 credits
```

Client sends request.

Your server processes it.

But network response is lost.

Client retries.

Now you potentially charge:

```
40 credits
```

even though the customer intended one operation.

Support:

```
Idempotency-Key: 7f3c...
```

Store:

```
idempotency_key
organization_id
request_hash
response
status
expires_at
```

Then retrying the same request can return the previous result instead of charging twice.

---

# 22. Usage events

Don't only store:

```
total = 8392
```

Store events.

Example:

```
{
  "request_id": "req_82ks...",
  "organization_id": "org_123",
  "api_key_id": "key_456",
  "endpoint": "/v1/generate",
  "units": 20,
  "status": 200,
  "latency_ms": 382,
  "timestamp": "..."
}
```

Then you can build:

```
Dashboard

Requests today: 38,291
Credits used: 72,892

/v1/search       30,221
/v1/generate      7,100
/v1/embed         970
```

---

# 23. Don't let analytics become your billing system

This is another common mistake.

You might have:

```
Kafka
  ↓
ClickHouse
  ↓
Grafana
```

for analytics.

Great.

But don't say:

> "Let's calculate the customer's balance from ClickHouse."

Instead:

```
Billing ledger
     ↓
Postgres
```

is authoritative.

Analytics:

```
Usage events
     ↓
Kafka
     ↓
ClickHouse
```

is optimized for querying.

So:

```
Postgres
= financial truth

ClickHouse
= analytics truth
```

---

# 24. Where Redis fits exactly

A good Redis layout might look like:

```
api_key:{hash}
```

Value:

```
{
  "organization_id": "org_123",
  "key_id": "key_456",
  "status": "active",
  "plan_id": "starter"
}
```

TTL:

```
5 minutes
```

Then:

```
rate:{org_id}:sec
rate:{org_id}:minute
```

And potentially:

```
quota:{org_id}
```

But again, **don't blindly put permanent credit balances only in Redis**.

---

# 25. What if Redis goes down?

This is where production engineering gets interesting.

You need to decide:

### Fail open

```
Redis unavailable
     ↓
allow request
```

Bad for expensive APIs because users could potentially bypass limits.

### Fail closed

```
Redis unavailable
     ↓
reject request
```

Safer financially, but hurts availability.

### Hybrid

For example:

```
normal:
Redis → rate limit

Redis failure:
local emergency limiter
+
strict circuit breaker
```

Your choice depends on how expensive each API call is.

For a $0.00001 API call, you may tolerate a tiny amount of overshoot.

For a $5 GPU inference call, absolutely not.

---

# 26. API Gateway alternatives

You don't necessarily need to write all this middleware yourself.

There are roughly **three approaches**.

## Option A — Build it yourself

```
Nginx / Envoy
      ↓
Your API
      ↓
Redis
      ↓
Postgres
```

You implement:

```
API key authentication
rate limiting
quota
billing
usage
```

### Pros

Maximum control.

### Cons

You own everything.

---

# 27. Option B — API Gateway

Examples include:

- AWS API Gateway
- Kong
- Envoy-based gateways
- Tyk
- Apigee
- Cloudflare API Gateway

For example, AWS API Gateway has built-in concepts for API keys, usage plans, throttling and quotas.

Kong provides key authentication and consumer-level rate limiting.

Architecture:

```
Internet
   ↓
Kong / AWS API Gateway
   ↓
Your services
```

This can remove a lot of infrastructure code.

---

# 28. Option C — API monetization platform

If you're actually building a company around selling APIs, there are specialized platforms that provide pieces of:

```
API keys
billing
metering
rate limiting
developer portal
plans
usage
```

Examples worth investigating include:

```
Stripe
AWS API Gateway
Kong
Tyk
Apigee
Cloudflare
Lago
Orb
OpenMeter
```

But they solve **different portions** of the problem.

Don't assume one product should own everything.

---

# 29. A strong modern architecture

If **you are building the platform yourself**, I'd recommend something like:

```
                 ┌─────────────────┐
                 │     Stripe      │
                 │    Payments     │
                 └────────┬────────┘
                          │ webhook
                          ▼
┌──────────┐       ┌───────────────┐
│ Customer │──────>│ API Platform  │
└──────────┘       └───────┬───────┘
                           │
                ┌──────────┼──────────┐
                ▼          ▼          ▼
             Postgres    Redis      Kafka
                │          │          │
                │          │          ▼
                │          │      Usage workers
                │          │          │
                │          │          ▼
                │          │      ClickHouse
                │          │
                ▼          ▼
          Billing truth   Runtime
                           limits
                │
                ▼
             API services
```

---

# 30. I'd use these technologies

If you're building this in **Go**, for example:

```
Language:
Go

API:
Gin / Chi / Fiber

Database:
PostgreSQL

Cache:
Redis

Queue:
Kafka / Redpanda / NATS

Analytics:
ClickHouse

Payments:
Stripe

Gateway:
Kong / Envoy / Cloudflare

Observability:
Prometheus
Grafana
OpenTelemetry

Deployment:
Kubernetes
```

You don't need all of these on day one.

---

# 31. Start much simpler

For your first production version:

```
                ┌─────────────┐
                │   Stripe    │
                └──────┬──────┘
                       │
                       ▼
                 Your Backend
                  /        \
                 /          \
                ▼            ▼
          PostgreSQL       Redis
             │               │
             │               │
       billing/keys       rate limits
       credits/usage
             │
             ▼
          Your API
```

That's enough.

Don't start with:

```
Kafka
Kubernetes
ClickHouse
multi-region
service mesh
10 microservices
```

unless you actually need them.

---

# 32. The database tables I'd actually start with

For your MVP:

```
users
organizations
api_keys
plans
subscriptions
credit_accounts
credit_ledger
usage_events
```

That's enough to build a serious first version.

Then:

```
Redis
```

for:

```
rate limiting
API-key cache
idempotency
```

Then later:

```
Kafka
ClickHouse
```

when usage becomes large.

---

# 33. The most important design principle

Separate these four numbers:

```
1. RATE
   How quickly can they call?

2. QUOTA
   How many calls/credits do they have?

3. BALANCE
   How much prepaid money/credit remains?

4. USAGE
   How much have they consumed historically?
```

For example:

```
Customer:

Rate:
20 req/sec

Quota:
100,000 credits/month

Balance:
62,381 credits

Historical usage:
37,619 credits
```

These should **not** be one Redis integer.

---

# 34. If you're building an AI API, it gets even more interesting

Suppose your API is:

```
POST /v1/chat
```

You could meter:

```
input_tokens
output_tokens
model
```

Example:

```
GPT-like model:

Input:
10,000 tokens

Output:
2,000 tokens
```

Then:

```
cost =
input_tokens × input_price
+
output_tokens × output_price
```

Your usage event becomes:

```
{
  "model": "my-model",
  "input_tokens": 10000,
  "output_tokens": 2000,
  "cost": 37
}
```

where `37` might mean 37 internal credits.

This architecture then scales naturally from:

```
$5 → 10,000 API calls
```

to:

```
$5 → variable AI usage
```

---

# 35. One subtle but VERY important distinction

There are actually two systems:

### Control plane

```
Dashboard
Users
Organizations
API keys
Plans
Billing
Subscriptions
Permissions
```

### Data plane

```
Incoming API requests
Authentication
Rate limiting
Authorization
Quota enforcement
Actual API execution
Usage metering
```

So:

```
             CONTROL PLANE
       ┌───────────────────────┐
       │ Users                 │
       │ API Keys              │
       │ Plans                 │
       │ Billing               │
       │ Dashboard             │
       └───────────┬───────────┘
                   │
                   ▼
             DATA PLANE
       ┌───────────────────────┐
       │ API Gateway           │
       │ Auth                  │
       │ Rate limiting         │
       │ Quota                 │
       │ API execution         │
       └───────────────────────┘
```

This distinction becomes **extremely important** once your API platform gets large.

---

# 36. If I were building your system

I'd build it in these phases:

### Phase 1 — API key system

```
Postgres
    ↓
users
organizations
api_keys

Generate:
sk_live_xxxxx

Hash key
Store hash
Authenticate request
Revoke key
Rotate key
```

### Phase 2 — Plans

```
plans
subscriptions

Free
Starter
Pro
Enterprise
```

### Phase 3 — Credits

```
credit_accounts
credit_ledger

$5
 ↓
10,000 credits
```

Atomic deduction.

### Phase 4 — Redis rate limiting

```
10 req/sec
100 req/min
```

### Phase 5 — Usage tracking

```
request_id
api_key
endpoint
latency
status
credits
```

### Phase 6 — Stripe

```
Checkout
 ↓
Payment
 ↓
Webhook
 ↓
Credits
```

### Phase 7 — Idempotency

```
Idempotency-Key
```

### Phase 8 — Gateway

Move common enforcement to:

```
Kong / Envoy / Cloudflare / AWS API Gateway
```

### Phase 9 — Event pipeline

```
API
 ↓
Kafka/Redpanda
 ↓
Usage workers
 ↓
Postgres + ClickHouse
```

### Phase 10 — Enterprise features

```
Multiple API keys
Scopes
Teams
SSO
IP allowlists
Key rotation
Webhooks
Budgets
Alerts
Audit logs
Per-endpoint pricing
Multiple environments
```

---

## The mental model I want you to keep

Think of your system as:

```
                     CUSTOMER
                        │
                    pays $5
                        │
                        ▼
                     STRIPE
                        │
                     webhook
                        │
                        ▼
                  CREDIT LEDGER
                    +10,000
                        │
                        │
Customer ── API KEY ──>│
                        ▼
                 ┌──────────────┐
                 │ API GATEWAY  │
                 └──────┬───────┘
                        │
             ┌──────────┼──────────┐
             ▼          ▼          ▼
          Auth       Rate       Credits
          Redis      Redis      Postgres
             │          │          │
             └──────────┼──────────┘
                        ▼
                    API SERVER
                        │
                        ▼
                   API RESPONSE
                        │
                        ▼
                   USAGE EVENT
                        │
                        ▼
                 Usage / Analytics
```

**Postgres = financial/source-of-truth state.**  
**Redis = fast enforcement state.**  
**Stripe = payment authority.**  
**Gateway = traffic/auth/rate-control layer.**  
**Usage ledger = auditability.**  
**Kafka/ClickHouse = scale/analytics when you need them.**

And importantly, **API keys themselves are not your billing system**. The API key identifies the caller; the organization/customer owns the plan and credit account; the usage system meters consumption.

If you're building this as an actual backend project, the next useful step would be to design the **exact PostgreSQL schema + Redis key structure + request middleware flow + atomic credit deduction algorithm**, including the race-condition cases.