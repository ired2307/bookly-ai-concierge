# Bookly AI Concierge

Aria is a customer support agent for a fictional online bookstore. It answers policy questions, retrieves order status and resolves an authenticated damaged delivery through a confirmed refund, while Bookly's application controls identity, data access and transaction authority.

Built with FastAPI and the Anthropic Messages API over direct HTTP. No Anthropic SDK and no agent framework. The repository includes 67 offline tests that run without a live API key.

---

## The problem it solves

Retail support conversations often begin with simple questions and end in actions that carry very different levels of risk. A customer may ask about delivery times, track an order or request money back for a damaged item. A useful agent should handle that journey without treating every request as equally trusted.

Bookly AI Concierge demonstrates three levels of authority in one conversation:

| A customer asks | What happens |
| --- | --- |
| *"How long does standard delivery take?"* | Aria retrieves Bookly's shipping policy and answers from the supplied policy data. |
| *"Where is my order?"* | A guest provides an order number and matching email address. Aria returns delivery status, carrier, tracking number and estimated delivery date. |
| *"My book arrived damaged."* | A guest is asked to sign in. The refund tool is not available in a guest session. |
| *"My book in order BK-10105 arrived damaged."* | A signed in customer has ownership and eligibility checked. Aria prepares the refund, but the application waits for explicit customer confirmation before executing it. |
| *"I need a person."* | Aria creates a structured handoff containing the reason and conversation summary. |

Context carries across each session, but authority does not come from conversation text. It comes from customer context created by the application.

### Why that matters

**Resolution rather than response.** The damaged delivery journey does not stop at quoting a policy. It validates the order, prepares an eligible action and completes it only after customer confirmation.

**Useful access without broad access.** Guests can retrieve delivery status after matching an order number and email address, but they cannot retrieve refund state, item values or return eligibility.

**Predictable actions.** The model interprets the request and selects a tool. Deterministic application code controls identity, ownership, eligibility, confirmation and idempotency.

---

## See it

Requires Python 3.11 or later and an Anthropic API key.

```bash
git clone https://github.com/ired2307/bookly-ai-concierge.git
cd bookly-ai-concierge

python -m venv .venv
```

Activate the environment:

```bash
# macOS or Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install dependencies and create a local configuration file:

```bash
pip install -r requirements.txt

# macOS or Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Add your own key to `.env`. If required, set `CLAUDE_MODEL` to a model available in your Anthropic account.

```text
ANTHROPIC_API_KEY=your-api-key-here
CLAUDE_MODEL=claude-sonnet-5
```

Start the application:

```bash
python -m uvicorn server:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Try the two demonstration journeys

**Guest order status**

Select **Guest** and send:

```text
Where is my order?
```

Then provide:

```text
BK-10042, jane.doe@email.com
```

**Authenticated damaged delivery**

Select **Sarah Lee** and send:

```text
My book in order BK-10105 arrived damaged.
```

Aria prepares a refund of $15.99. The browser presents a confirmation control, and the refund is executed only after the customer selects **Confirm refund**.

Bookly, its customers, orders and transactions are synthetic.

---

## The engineering principle

> **Authority is a server side capability, not a prompt instruction.**

A prompt can tell a model not to perform an action, but that instruction is not an authorisation boundary. The model processes customer supplied text and can make mistakes. The application therefore decides which tools exist for a session and validates every consequential action again when the tool runs.

The available tool set is built from server held customer context:

```python
def tool_definitions_for(ctx: CustomerContext) -> list[dict]:
    definitions = []
    for definition in TOOL_DEFINITIONS:
        if definition["name"] == "prepare_refund" and not ctx.authenticated:
            continue

        scoped = copy.deepcopy(definition)
        if scoped["name"] == "lookup_order" and not ctx.authenticated:
            scoped["input_schema"]["required"] = ["order_id", "customer_email"]

        definitions.append(scoped)
    return definitions
```

This produces two different capability surfaces:

| Session | Available authority |
| --- | --- |
| Guest | Policy search, delivery status with order number plus matching email, human handoff |
| Signed in | Policy search, owned order details, refund preparation, human handoff |

The model never receives `authenticated`, `customer_id`, `session_id` or the refund confirmation token as tool inputs. Those values are injected by the orchestration layer from application state.

### Data is scoped as well as actions

The same order lookup returns different fields according to the customer's authority.

A guest receives delivery fields only:

```text
id, status, order_date, shipped_date,
delivered_date, estimated_delivery, tracking_number, carrier
```

The authenticated owner may additionally receive item details, total value, return eligibility and existing refund status. Unknown orders, mismatched email addresses and orders belonging to another signed in customer all return the same generic lookup failure, reducing order enumeration risk.

### Confirmation is outside the model

Refund preparation and refund execution are separate operations:

1. `prepare_refund` validates authentication, ownership and eligibility.
2. The application creates a random confirmation token with a ten minute expiry.
3. The token is stored server side and scoped to the session, customer and order.
4. The browser receives only a safe refund summary, never the token.
5. The customer selects **Confirm refund**.
6. The application retrieves the token and calls `initiate_refund` directly.

The LLM cannot confirm or execute the refund. A consumed token cannot be reused, and a completed order is protected by an idempotency key so a retry returns the original result rather than creating a second refund.

That is the difference between asking the model to behave safely and designing the system so the model does not possess the authority to behave unsafely.

---

## How the agent loop works

`ConversationClient` calls the Anthropic Messages API directly with `requests`. Keeping the loop explicit makes the orchestration path easy to inspect:

1. The customer message is added to session history.
2. The model interprets the request and either responds or requests a tool.
3. The application validates and executes each requested tool.
4. Tool results are appended to the conversation.
5. The model observes the result and continues until it returns `end_turn`.

The loop supports multiple tool calls in one model response and is capped at ten tool rounds per customer turn. It does not request or expose private chain of thought.

```text
Browser or CLI
      |
      v
FastAPI session and channel layer
      |
      v
SupportAgent and direct HTTP tool loop
      |
      +--> lookup_order
      +--> prepare_refund       signed in only
      +--> search_policies
      +--> escalate_to_human
      |
      v
Synthetic order, policy and transaction state
```

### Why direct HTTP

The implementation intentionally avoids an Anthropic SDK and agent framework. The request payload, stop reasons, tool results, retry policy and conversation history remain visible in a small amount of Python. This is a demonstration choice, not a claim that frameworks should never be used.

---

## What is implemented

| Capability | Implementation |
| --- | --- |
| General policy enquiries | `search_policies` retrieves shipping, returns, password, payment and cancellation content from Bookly's policy data. |
| Guest order status | `lookup_order` requires `order_id` and `customer_email`, uses a generic failure response and returns delivery fields only. |
| Authenticated order status | Server held customer identity validates ownership. The customer does not need to provide an email address again. |
| Damaged delivery refund | `prepare_refund` validates authentication, ownership and eligibility before creating pending state. |
| Explicit confirmation | `/confirm/{session_id}` executes with a server held token only after the browser confirmation action. |
| Duplicate prevention | Completed refunds are idempotent and repeated preparation does not create another confirmation. |
| Human handoff | `escalate_to_human` produces a reason and conversation summary for downstream handoff. |
| Bounded execution | 4,000 character messages, 50 conversation turns, 10 tool rounds, 30 second provider timeout and two transient retries. |

---

## Testing

The 67 automated tests run offline with mocked Anthropic responses and a synthetic test key.

```bash
pytest -q
```

The suite covers:

* Tool input validation and unknown tool handling
* Guest email matching and generic lookup failures
* Guest data minimisation
* Authenticated ownership enforcement
* Context specific tool availability
* Guest refund denial even when the model attempts the tool
* Confirmation token presence, expiry and session, customer and order scope
* Idempotent refund execution
* Transient retry and permanent error behaviour
* Multi turn agent trajectories
* Session, chat and confirmation endpoint control flow



---

## Security controls demonstrated

**Least privilege tool exposure.** Guest sessions do not receive the refund tool definition.

**Server held identity.** Authentication and customer identity are created by the application and are absent from model controlled tool arguments.

**Defence in depth.** Refund tools and the confirmation endpoint validate authentication and ownership even though the tool is already hidden from guests.

**Scoped disclosure.** Guest order lookup returns delivery data only. Refund state, order value and eligibility remain restricted to the authenticated owner.

**Enumeration resistance.** Unknown orders, mismatched emails and unauthorised ownership return the same lookup error.

**Explicit consent.** Refund execution requires an application controlled confirmation action using a server held token.

**Replay protection.** Confirmation tokens expire, are scoped to one session, customer and order, and are marked as consumed after use.

**Bounded work.** Message length, conversation length, provider timeout, retry budget and agent loop length are capped.

**Safe browser rendering.** Customer and model supplied text is inserted with `textContent`, not interpreted as HTML. The only `innerHTML` use creates a fixed typing indicator and does not contain model output.

**Credential separation.** The repository includes `.env.example` only. `.env` is ignored by Git and the API key remains server side.

---

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Serve the browser interface |
| `POST` | `/session` | Create a server generated guest or Sarah demo session |
| `POST` | `/chat` | Send a message through an active session |
| `POST` | `/confirm/{session_id}` | Confirm and execute a prepared refund |
| `DELETE` | `/session/{session_id}` | End a session and clear its pending confirmation state |

---

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | Yes | None | Anthropic API authentication |
| `CLAUDE_MODEL` | No | `claude-sonnet-5` | Model supplied to the Messages API |
| `MAX_TOKENS` | No | `1024` | Maximum tokens requested per provider response |
| `MAX_TOOL_STEPS` | No | `10` | Maximum tool loop rounds per customer turn |

---

## Repository structure

```text
bookly-ai-concierge/
├── agent.py               System instructions and context scoped tool set
├── client.py              Direct HTTP Anthropic client and agent loop
├── context.py             Server held customer context
├── tools.py               Tool schemas, validation and business controls
├── data.py                Synthetic orders, policies and transaction state
├── config.py              Environment configuration and execution limits
├── server.py              FastAPI sessions, chat and confirmation endpoints
├── cli.py                 Command line interface
├── static/
│   └── index.html         Browser chat interface
├── evals/
│   └── test_journeys.py   Scripted multi turn trajectory evaluations
├── test_tools.py          Tool, client and authority tests
├── test_server.py         Endpoint control flow tests
└── test_scenarios.py      Live smoke scenarios
```

---

## Prototype boundaries and production path

This repository is deliberately a proof of concept. It demonstrates the control pattern without pretending to provide production infrastructure.

| Prototype boundary | Production approach |
| --- | --- |
| Fixed synthetic guest and Sarah profiles | Validate the channel identity or session token and derive customer context server side |
| In memory conversation state | Use a durable customer scoped session store with expiry and deletion controls |
| In memory orders and refunds | Integrate governed order and payment services with transactional writes and reconciliation |
| Keyword policy matching | Use governed knowledge ingestion, retrieval evaluation and source attribution |
| Single process runtime | Use shared state that supports multiple workers and safe concurrent confirmation |
| Local tool traces | Emit structured traces for latency, model usage, tool outcomes, policy decisions and handoff reasons |
| Offline scripted evaluations | Add representative production journeys, model based quality graders, regression gates and canary releases |
| Basic bounded retries | Add service specific timeouts, circuit breakers, queues and operational alerting |
| No public endpoint rate limiting | Add identity aware rate limits, abuse protection and spend controls before external exposure |

The production principle remains unchanged: the model interprets intent and manages the conversation, while trusted systems control identity, facts, policy, customer consent and action authority.

---


