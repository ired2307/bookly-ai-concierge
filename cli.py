"""Entry point — interactive REPL for the Bookly support agent."""
import json
import logging

from agent import SupportAgent
from context import CustomerContext
from data import PENDING_REFUNDS
from tools import initiate_refund

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# CLI sessions run as authenticated for demo purposes
_CLI_CTX = CustomerContext(
    session_id="cli-session",
    authenticated=True,
    customer_id="CUST-004",
)


def main() -> None:
    agent = SupportAgent(ctx=_CLI_CTX)
    logger.info("CLI session started (authenticated demo customer)")

    print("=" * 56)
    print("  Bookly Customer Support  |  Aria (AI Agent)")
    print("  'confirm' → approve prepared refund")
    print("  'new' → reset conversation  |  'quit' → exit")
    print("=" * 56)
    print("\nAria: Hi! Welcome to Bookly support. How can I help you today?\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nAria: Thanks for contacting Bookly. Have a great day!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("\nAria: Thanks for contacting Bookly. Have a great day!")
            break

        if user_input.lower() == "new":
            agent.reset()
            _clear_pending_refunds()
            print("\n" + "=" * 56)
            print("  New conversation started")
            print("=" * 56)
            print("\nAria: Hi! How can I help you today?\n")
            continue

        if user_input.lower() == "confirm":
            print(f"\nAria: {_confirm_pending_refund()}\n")
            continue

        print()
        reply = agent.reply(user_input)
        print(f"Aria: {reply}\n")

def _confirm_pending_refund() -> str:
    pending = next(
        (
            (token, data)
            for token, data in reversed(list(PENDING_REFUNDS.items()))
            if data["session_id"] == _CLI_CTX.session_id and not data.get("consumed")
        ),
        None,
    )
    if not pending:
        return "There is no refund awaiting confirmation."
    token, data = pending
    result = json.loads(initiate_refund(data["order_id"], _CLI_CTX, token))
    return result.get("message", result.get("error", "The refund could not be processed."))


def _clear_pending_refunds() -> None:
    for token, data in list(PENDING_REFUNDS.items()):
        if data["session_id"] == _CLI_CTX.session_id:
            PENDING_REFUNDS.pop(token, None)


if __name__ == "__main__":
    main()
