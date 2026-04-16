"""
Nykaa Coupon Code Verifier — Browser Use Cloud edition
Usage:
  python verify_nykaa_coupon.py --code SAVE10
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

PRODUCT_URL   = os.getenv(
    "NYKAA_PRODUCT_URL",
    "https://www.nykaa.com/dr-sheth-s-ceramide-vitamin-c-sunscreen/p/5237430",
)
NYKAA_HOME    = "https://www.nykaa.com"
POLL_INTERVAL    = 5
MAX_WAIT         = 300
LLM_MODEL        = os.getenv("BU_LLM", "gemini-2.5-flash")
NYKAA_EMAIL      = os.getenv("NYKAA_EMAIL", "")
NYKAA_PASSWORD   = os.getenv("NYKAA_PASSWORD", "")


# ---------------------------------------------------------------------------
# Verify coupon
# ---------------------------------------------------------------------------

async def verify(code: str) -> dict:
    print(f"\nVerifying: {code!r}")

    client = AsyncBrowserUse(api_key=API_KEY)

    session = await client.sessions.create_session(keep_alive=True)
    print(f"\n  🌐 Watch live: {session.live_url}\n")

    # Build login instruction only if credentials are provided
    login_step = ""
    if NYKAA_EMAIL and NYKAA_PASSWORD:
        login_step = f"""1. Go to {NYKAA_HOME} and log in using:
   - Email: {NYKAA_EMAIL}
   - Password: {NYKAA_PASSWORD}
   After logging in, continue to the next step.
"""

    task_prompt = f"""
You are verifying whether the Nykaa coupon code "{code}" is valid.

Follow these steps:
{login_step}{"2" if login_step else "1"}. Navigate to the product page: {PRODUCT_URL}
2. Click the bag/cart icon in the header to open the bag sidebar.
3. In the sidebar, click "Apply now and save extra!" to open the coupons panel.
4. In the coupon input field, type "{code}".
   Note: this is a React-controlled input. If typing doesn't register, use JavaScript to set the value via the native HTMLInputElement setter and dispatch an input event with bubbles:true.
5. Click the "Collect" or "Apply" button to submit.
6. Wait for the result to appear.
7. Return a JSON object with ONLY these two fields:
   - "valid": true if the coupon was accepted, false otherwise
   - "message": the exact success or error text shown on the page

Return ONLY the JSON. Example:
{{"valid": true, "message": "Coupon applied successfully"}}
"""

    secrets = {}
    if NYKAA_EMAIL and NYKAA_PASSWORD:
        secrets = {"nykaa_email": NYKAA_EMAIL, "nykaa_password": NYKAA_PASSWORD}

    created = await client.tasks.create_task(
        task=task_prompt,
        session_id=session.id,
        llm=LLM_MODEL,
        secrets=secrets or None,
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
    print(f"  Task created: {task_id}  |  Model: {LLM_MODEL}")

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
        await client.sessions.update_session(session.id, action=SessionUpdateAction.STOP)

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nykaa Coupon Verifier (Browser Use Cloud)")
    parser.add_argument("--code", type=str, required=True, help="Coupon code to verify")
    args = parser.parse_args()

    result = asyncio.run(verify(args.code.strip().upper()))
    print("\n" + "=" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 50)


if __name__ == "__main__":
    main()
