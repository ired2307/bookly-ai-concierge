# Bookly AI Concierge

Aria is a customer support agent for Bookly, a fictional online bookstore. It uses a conversational model to interpret customer intent and a small set of scoped tools to retrieve order data, search policy and prepare approved actions.

The implementation calls the Anthropic Messages API directly over HTTP. It does not use an Anthropic SDK or an agent framework, keeping the orchestration loop visible and easy to inspect.

## Demonstration scope

The proof of concept covers two customer journeys:

1. A guest tracks an order using an order number and matching email address.
2. A signed in customer reports a damaged delivery, reviews an eligible refund and confirms the transaction through the application.

Bookly, its customers and its order data are synthetic. Authentication is simulated through two fixed demo profiles. The implementation is intended to demonstrate conversational orchestration, scoped tool use, progressive authority and application controlled confirmation rather than production infrastructure.

## Run locally

Requires Python 3.11 or later.

```bash
git clone https://github.com/ired2307/bookly-ai-concierge.git
cd bookly-ai-concierge
pip install -r requirements.txt
cp .env.example .env
# Add your own ANTHROPIC_API_KEY to .env
python -m uvicorn server:app --reload
```

Open `http://127.0.0.1:8000`.

The repository contains no API credentials. Each reviewer supplies their own key through `.env`, which is excluded from version control.

The command line interface is also available:

```bash
python cli.py
```

## Demo journeys

### Guest order tracking

Select **Guest** and enter:

```text
Where is my order?
BK-10042, jane.doe@email.com
```

The agent asks for missing information, calls `lookup_order` only when both identifiers are present and returns the scoped delivery details.

### Damaged delivery

Select **Sarah Lee** and enter:

```text
My book in order BK-10105 arrived damaged.
```

The agent prepares an eligible refund of $15.99. The interface then presents a confirmation control. Refund execution occurs only after the customer uses that control.

## Architecture

```text
Browser or CLI
      │
      ▼
FastAPI session and channel layer
      │
      ▼
SupportAgent and direct HTTP agent loop
      │
      ├── lookup_order
      ├── prepare_refund
      ├── search_policies
      └── escalate_to_human
      │
      ▼
Synthetic orders, policies and transaction state
```

`ConversationClient` posts the conversation, system instructions and JSON tool schemas to the Anthropic Messages API. When the model returns `tool_use`, the application validates and executes the requested tool, appends the result to conversation history and continues the loop. A final `end_turn` response is returned to the channel.

## Design decisions

### One conversational agent with scoped tools

A single agent maintains context across the support journey. Its available tools are narrow, typed and independently testable. Customer authority and business rules are injected by the application rather than supplied by the model.

### Progressive authority

Policy enquiries are available to every customer. Guest order tracking requires an order number and matching email address and returns delivery fields only. Signed in customers are authorised through server held customer context and can retrieve their own order details without re-entering an email address. The refund tool is not exposed to guest sessions. Refund preparation additionally validates authentication and order ownership at execution time. The model cannot create or modify customer context because it is absent from the tool schemas.

### Application controlled confirmation

Refund preparation and execution are separate operations:

1. `prepare_refund` validates authentication, ownership and eligibility.
2. The application stores a short lived confirmation token in `PENDING_REFUNDS`.
3. The customer reviews the refund details and confirms through the interface.
4. The application calls `initiate_refund` with the server held token.

The token is never exposed to the model or returned to the browser. The model can propose an eligible action, but it cannot confirm or execute the transaction.

### Idempotent refund execution

A completed refund stores its result against the order. Repeated confirmation returns the original result rather than executing the transaction again.

### Bounded execution and failure handling

The tool loop has a maximum of ten steps. Anthropic requests retry transient failures within a separate bounded budget and do not retry permanent request errors. Tool inputs are validated before dispatch, provider errors are sanitised and unexpected stop reasons return a controlled handoff response.

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Serve the browser interface |
| `POST` | `/session` | Create a server generated guest or Sarah demo session |
| `POST` | `/chat` | Send a message using an active session |
| `POST` | `/confirm/{session_id}` | Confirm and execute a prepared refund |
| `DELETE` | `/session/{session_id}` | End a session and clear its pending state |

## Tests

All automated tests run offline with mocked Anthropic responses and a synthetic test key:

```bash
pytest -v
```

The suite covers tool validation, guest and authenticated authority, enumeration resistance, confirmation token scope and expiry, idempotency, retry behaviour, agent trajectories and endpoint control flow.

Live smoke scenarios can be run separately when an Anthropic key is configured:

```bash
python test_scenarios.py
```

## Repository structure

```text
bookly-agent/
├── agent.py
├── client.py
├── context.py
├── tools.py
├── data.py
├── config.py
├── server.py
├── cli.py
├── test_scenarios.py
├── test_tools.py
├── test_server.py
├── evals/
│   └── test_journeys.py
└── static/
    └── index.html
```

## Prototype boundaries and production path

| Prototype boundary | Production approach |
|---|---|
| Fixed synthetic demo identities | Validate the channel session or identity token and derive customer context server side |
| In memory conversation state | Use a durable, customer scoped session store with expiry |
| In memory orders and refunds | Integrate governed order and payment services with transactional writes |
| Single process runtime | Use a shared state store that supports multiple application workers |
| Local tool traces | Add structured traces for latency, token usage, tool outcomes and handoff reasons |
| Offline deterministic evaluations | Add representative production journeys, model based quality grading, regression gates and canary releases |
| Basic bounded retries | Add service specific timeouts, circuit breakers and operational alerting |

The production principle remains the same: the model interprets intent and selects approved tools, while trusted systems control identity, policy, customer consent and transaction authority.
