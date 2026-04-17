"""
Nykaa Coupon Code Verifier — Playwright login + Browser Use Cloud task
Usage:
  python verify_nykaa_coupon.py --code SAVE10

Requires BROWSER_USE_API_KEY in .env
Flow:
  1. Local Playwright browser opens nykaa.com — you log in
  2. Cookies are extracted and injected into Browser Use cloud session
  3. Cloud agent verifies the coupon already authenticated
"""

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from browser_use_sdk import AsyncBrowserUse
from browser_use_sdk.types.session_update_action import SessionUpdateAction

load_dotenv()

API_KEY     = os.getenv("BROWSER_USE_API_KEY", "")
PRODUCT_URL = os.getenv(
    "NYKAA_PRODUCT_URL",
    "https://www.nykaa.com/dr-sheth-s-ceramide-vitamin-c-sunscreen/p/5237430",
)
NYKAA_HOME  = "https://www.nykaa.com"
PROFILE_DIR = os.path.abspath("nykaa_profile")


async def get_nykaa_cookies() -> list:
    """Open local browser, let user log in, return cookies."""
    print("\n[Step 1] Opening local browser for Nykaa login...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=False,
            args=["--start-maximized"],
            ignore_default_args=["--enable-automation"],
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(NYKAA_HOME)
        print(">>> Nykaa is open in the browser window.")
        print(">>> Please log in to Nykaa.")
        input(">>> Press Enter once you are logged in...")
        cookies = await context.cookies([NYKAA_HOME, "https://www.nykaa.com"])
        await browser.close()
    print(f"[Step 1] Done — extracted {len(cookies)} cookies.")
    return cookies


async def verify(code: str) -> dict:
    print(f"\nVerifying coupon: {code!r}")

    # Step 1: Get cookies from local login
    cookies = await get_nykaa_cookies()

    # Step 2: Create Browser Use cloud session
    print("\n[Step 2] Creating cloud browser session...")
    client = AsyncBrowserUse(api_key=API_KEY)
    session = await client.sessions.create_session(keep_alive=True)
    print(f">>> Watch live: {session.live_url}")

    # Build cookie injection JS
    cookie_js = "; ".join(
        f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value")
    )

    task_prompt = f"""
You are verifying whether the Nykaa coupon code "{code}" is valid.

First, inject login cookies so you appear logged in:
1. Go to https://www.nykaa.com
2. Run this JavaScript in the browser console to set cookies:
   document.cookie = "{cookie_js}; path=/; domain=.nykaa.com"
3. Reload the page and confirm you are logged in (look for user account icon).

Then verify the coupon:
4. Navigate to: {PRODUCT_URL}
5. Click the bag/cart icon in the header to open the bag sidebar.
6. In the sidebar, click "Apply now and save extra!" to open the coupons panel.
7. In the coupon input field, type "{code}".
   If the React input doesn't register typing, use JavaScript:
   var input = document.querySelector('input[placeholder*="coupon"], input[placeholder*="promo"]');
   Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, '{code}');
   input.dispatchEvent(new Event('input', {{bubbles: true}}));
8. Click "Collect" or "Apply" button.
9. Wait for the result message.
10. Return ONLY a JSON object:
    {{"valid": true, "message": "exact success message"}}
    or
    {{"valid": false, "message": "exact error message"}}
"""

    try:
        print("\n[Step 3] Running coupon verification task...")
        task = await client.tasks.create_task(
            task=task_prompt,
            session_id=session.id,
        )
        print(f"Task ID: {task.id}")

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
        # Strip excess backslash escaping
        while "\\\"" in raw:
            raw = raw.replace("\\\"", "\"")
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
    parser = argparse.ArgumentParser(description="Nykaa Coupon Verifier")
    parser.add_argument("--code", type=str, required=True, help="Coupon code to verify")
    args = parser.parse_args()

    result = asyncio.run(verify(args.code.strip().upper()))
    print("\n" + "=" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 50)


if __name__ == "__main__":
    main()
