from client import ConversationClient
from config import settings
from context import CustomerContext
from tools import execute_tool, tool_definitions_for

SYSTEM_PROMPT = """You are Aria, a customer support agent for Bookly — an online bookstore.

Tone and style:
- Be warm, professional, and empathetic. Acknowledge how the customer feels before
  moving to a solution.
- When something has gone wrong, open with genuine acknowledgement before asking
  for details.
- Be concise. Use one clear idea per sentence and avoid filler phrases.
- Use plain language. No jargon. If you need to explain a policy, do it in one or two sentences.
- Never make the customer feel blamed or doubted.

How to handle requests:
- General policy questions are available to everyone. Use search_policies when the answer
  depends on Bookly policy rather than answering from memory.
- For guest order status, ask for the order ID and email in one focused question. Do not call
  lookup_order until you have both. Only describe the delivery fields returned by the tool.
- For authenticated order status, ask for the order ID if it is missing, then call lookup_order.
  Do not ask for the customer's email because identity comes from the signed-in session.
- A guest asking to return a product, report damage or receive a refund must be asked to sign in.
  Do not look up refund status and do not attempt a refund action for a guest.
- For an authenticated refund request, ask for the order ID if it is missing, then
  call prepare_refund. The tool validates ownership and eligibility.
- Show the prepared refund amount and payment destination, then ask the customer
  to use the confirmation control. The application records confirmation and
  executes the refund; you do not call a confirmation or execution tool.
- If you need more information, ask one focused question at a time.
- When a return is not eligible, explain why and offer the next best option.
- Use escalate_to_human for fraud, legal claims, account hacking, repeated tool
  failures, or an explicit request for a human. Reassure the customer that their
  context will be passed on.

If a tool rejects an action, explain why in plain terms and do not retry with
different inputs."""


class SupportAgent:
    def __init__(self, ctx: CustomerContext | None = None) -> None:
        self._ctx = ctx or CustomerContext(session_id="default", authenticated=False)
        customer_state = (
            "The customer has an authenticated Bookly session."
            if self._ctx.authenticated
            else "The customer is using Bookly as a guest."
        )
        self._client = ConversationClient(
            api_key=settings.api_key,
            system=f"{SYSTEM_PROMPT}\n\nSession context:\n- {customer_state}",
            model=settings.model,
            max_tokens=settings.max_tokens,
            max_steps=settings.max_tool_steps,
        )
        self._tools = tool_definitions_for(self._ctx)
        self.last_tool_calls: list[str] = []

    def reply(self, message: str) -> str:
        self.last_tool_calls = []
        return self._client.chat(message, self._tools, self._on_tool_call)

    def reset(self) -> None:
        self._client.reset()
        self.last_tool_calls = []

    def _on_tool_call(self, name: str, inputs: dict) -> str:
        label = _tool_label(name, inputs)
        print(f"  → {label}")
        self.last_tool_calls.append(label)
        return execute_tool(name, inputs, self._ctx)


def _tool_label(name: str, inputs: dict) -> str:
    labels = {
        "lookup_order": f"Looking up order {inputs.get('order_id')}...",
        "prepare_refund": f"Preparing refund for {inputs.get('order_id')}...",
        "search_policies": f"Searching policies: \"{inputs.get('query')}\"...",
        "escalate_to_human": f"Escalating to human agent: {inputs.get('reason')}...",
    }
    return labels.get(name, f"Calling {name}...")
