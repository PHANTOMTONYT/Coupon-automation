"""
Amazon Coupon Code Verifier — Browser Use Cloud edition
Usage:
  python verify_amazon_coupon.py --code SAVE20
  python verify_amazon_coupon.py --code SAVE20 --asin B0CHX1W1XY

A live browser view URL will be printed — open it to watch the agent work in real-time.
"""

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv
from browser_use_sdk import AsyncBrowserUse
from browser_use_sdk.types.session_update_action import SessionUpdateAction

load_dotenv()

API_KEY = os.getenv("BROWSER_USE_API_KEY") or os.getenv("BROWSER_USE", "")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_ASIN  = os.getenv("AMAZON_ASIN", "B0CHX1W1XY")
AMAZON_BASE   = "https://www.amazon.in"
POLL_INTERVAL = 5    # seconds between status polls
MAX_WAIT      = 300  # seconds before giving up


# ---------------------------------------------------------------------------
# Verify coupon
# ---------------------------------------------------------------------------

async def verify(code: str, asin: str) -> dict:
    print(f"\nVerifying: {code!r}  |  ASIN: {asin}")

    client = AsyncBrowserUse(api_key=API_KEY)

    # Step 1 — create a session so we get a live view URL
    session = await client.sessions.create_session(keep_alive=True)
    print(f"\n  🌐 Watch live: {session.live_url}\n")

    task_prompt = f"""
You are verifying whether the Amazon coupon code "{code}" is valid on amazon.in.

Follow these steps:
1. Go to {AMAZON_BASE} and log in if needed.
2. Add the product with ASIN "{asin}" to cart by navigating to:
   {AMAZON_BASE}/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1
3. Go to the cart at {AMAZON_BASE}/gp/cart/view.html and confirm the item is present.
4. Click "Proceed to Buy" to reach the checkout page.
5. Find the coupon input (name="ppw-claimCode"), type "{code}", then click Apply (name="ppw-claimCodeApplyPressed").
6. Wait for the result to appear.
7. Return a JSON object with ONLY these two fields:
   - "valid": true if the coupon was applied successfully (e.g. "Promotion applied"), false otherwise
   - "message": the exact success or error text shown on the page

Return ONLY the JSON. Example:
{{"valid": true, "message": "Promotion applied"}}
"""

    # Step 2 — create the task inside the session
    created = await client.tasks.create_task(
        task=task_prompt,
        session_id=session.id,
        structured_output=json.dumps({
            "type": "object",
            "properties": {
                "valid":   {"type": "boolean"},
                "message": {"type": "string"}
            },
            "required": ["valid", "message"]
        }),
    )
    task_id = created.id
    print(f"  Task created: {task_id}")

    # Step 3 — poll until finished
    result = {"code": code, "valid": False, "message": "Timed out waiting for task to complete"}
    elapsed = 0
    try:
        while elapsed < MAX_WAIT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            status_view = await client.tasks.get_task_status(task_id)
            status = str(status_view.status)
            print(f"  Status [{elapsed}s]: {status}")

            if status in ("finished", "stopped", "failed"):
                output = getattr(status_view, "output", None)
                if not output:
                    result = {"code": code, "valid": False, "message": f"Task ended with status: {status}"}
                    break

                raw = str(output).strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                try:
                    result = {"code": code, **json.loads(raw.strip())}
                except json.JSONDecodeError:
                    result = {"code": code, "valid": False, "message": raw}
                break
    finally:
        # Step 4 — stop the session
        await client.sessions.update_session(session.id, action=SessionUpdateAction.STOP)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Amazon Coupon Verifier (Browser Use Cloud)")
    parser.add_argument("--code", type=str, required=True, help="Coupon/promo code to verify")
    parser.add_argument("--asin", type=str, default=DEFAULT_ASIN, help=f"Amazon ASIN (default: {DEFAULT_ASIN})")
    args = parser.parse_args()

    result = asyncio.run(verify(args.code.strip().upper(), args.asin))
    print("\n" + "=" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 50)


if __name__ == "__main__":
    main()
