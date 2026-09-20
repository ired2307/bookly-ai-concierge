"""Interactive smoke scenarios using the configured Anthropic model.

Run with ANTHROPIC_API_KEY set:
    python test_scenarios.py
"""
import json

from agent import SupportAgent
from context import CustomerContext
from data import PENDING_REFUNDS
from tools import initiate_refund


def conversation(title: str, turns: list[str], ctx: CustomerContext) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")
    agent = SupportAgent(ctx=ctx)
    for message in turns:
        print(f"\nCustomer: {message}")
        print(f"Aria: {agent.reply(message)}")


def damaged_delivery_refund() -> None:
    """Exercise preparation followed by application-controlled confirmation."""
    print(f"\n{'=' * 60}\n  Authenticated damaged delivery\n{'=' * 60}")
    ctx = CustomerContext(
        session_id="scenario-sarah",
        authenticated=True,
        customer_id="CUST-004",
    )
    agent = SupportAgent(ctx=ctx)
    message = "My book in order BK-10105 arrived damaged."
    print(f"\nCustomer: {message}")
    print(f"Aria: {agent.reply(message)}")

    pending = next(
        (
            (token, data)
            for token, data in PENDING_REFUNDS.items()
            if data["session_id"] == ctx.session_id and not data.get("consumed")
        ),
        None,
    )
    if not pending:
        print("\nApplication: No refund is awaiting confirmation.")
        return

    token, refund = pending
    print(
        f"\nCustomer confirms refund of ${refund['amount']:.2f} "
        f"for {refund['order_id']}."
    )
    result = json.loads(initiate_refund(refund["order_id"], ctx, token))
    print(f"Application: {result.get('message', result.get('error'))}")


if __name__ == "__main__":
    conversation(
        "Guest order tracking",
        ["Where is my order?", "BK-10042, jane.doe@email.com"],
        CustomerContext(session_id="scenario-guest", authenticated=False),
    )
    damaged_delivery_refund()
    conversation(
        "Policy question",
        ["How long does standard shipping take?"],
        CustomerContext(session_id="scenario-policy", authenticated=False),
    )
    conversation(
        "Human escalation",
        ["I think someone accessed my account without permission."],
        CustomerContext(session_id="scenario-escalation", authenticated=False),
    )
