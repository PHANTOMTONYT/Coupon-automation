"""
Amazon Coupon Code Verifier — Browser Use Cloud SDK
Usage:
  python verify_amazon_coupon.py --code SAVE20
  python verify_amazon_coupon.py --code SAVE20 --asin B0CHX1W1XY

Requires BROWSER_USE_API_KEY in .env
Opens a live cloud browser — prints a URL you can watch in real time.
"""

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv
from browser_use_sdk import AsyncBrowserUse
from browser_use_sdk.types.session_update_action import SessionUpdateAction

load_dotenv()

API_KEY      = os.getenv("BROWSER_USE_API_KEY", "")
DEFAULT_ASIN = os.getenv("AMAZON_ASIN", "B0CHX1W1XY")
AMAZON_BASE  = "https://www.amazon.in"


async def verify(code: str, asin: str) -> dict:
    print(f"\nVerifying: {code!r}  |  ASIN: {asin}")

    client = AsyncBrowserUse(api_key=API_KEY)

    # Create a persistent session so we get a live view URL
    session = await client.sessions.create_session(keep_alive=True)
    print(f"\n>>> Open this URL to watch the browser live:\n    {session.live_url}\n")

    task_prompt = f"""
You are verifying whether the Amazon coupon code "{code}" is valid on amazon.in.

Follow these steps exactly:
1. Go to {AMAZON_BASE}. Log in if needed.
2. Add the product with ASIN "{asin}" to cart by navigating to:
   {AMAZON_BASE}/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1
3. Go to the cart at {AMAZON_BASE}/gp/cart/view.html and confirm the item is present.
4. Click the "Proceed to Buy" button to go to checkout.
5. On the checkout page, find the coupon/promo code input field (name="ppw-claimCode").
6. Type the coupon code "{code}" into the field.
7. Click the Apply button (name="ppw-claimCodeApplyPressed").
8. Wait for the result to appear on the page.
9. Report the result as a JSON object:
   - "valid": true if the coupon was successfully applied, false otherwise
   - "message": the exact success or error message shown on the page

Return ONLY the JSON. Example:
{{"valid": true, "message": "Promotion applied"}}
or
{{"valid": false, "message": "The promotional code you entered is not valid."}}
"""

    try:
        task = await client.tasks.create_task(
            task=task_prompt,
            session_id=session.id,
        )
        print(f"Task created: {task.id}")

        # Poll until done
        while True:
            status = await client.tasks.get_task_status(task.id)
            state = getattr(status, "status", None) or getattr(status, "state", None)
            print(f"  Status: {state}")
            if state in ("finished", "stopped", "failed", "completed"):
                break
            await asyncio.sleep(5)

        output = getattr(status, "output", None) or getattr(status, "result", None)
        if not output:
            return {"code": code, "valid": False, "message": "No output from task"}

        raw = str(output).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        return {"code": code, **result}

    except json.JSONDecodeError:
        return {"code": code, "valid": False, "message": f"Could not parse result: {raw!r}"}
    except Exception as exc:
        return {"code": code, "valid": False, "message": f"Error: {exc}"}
    finally:
        try:
            await client.sessions.update_session(session.id, action=SessionUpdateAction.STOP)
        except Exception:
            pass


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
