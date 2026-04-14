"""
Amazon Coupon Code Verifier
Usage:
  python verify_coupon.py --code SAVE20
  python verify_coupon.py --code SAVE20 --asin B0CHX1W1XY
"""

import argparse
import json
import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ASIN        = "B0CHX1W1XY"
AMAZON_BASE = "https://www.amazon.in"
PROFILE_DIR = "browser_profile"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en'] });
window.chrome = { runtime: {} };
"""


# ---------------------------------------------------------------------------
# Verify coupon
# ---------------------------------------------------------------------------

def verify(code: str, asin: str) -> dict:
    print(f"\nVerifying: {code!r}  |  ASIN: {asin}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
            user_agent=USER_AGENT,
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.add_init_script(STEALTH_JS)

        # Open Amazon — user logs in if needed, then presses Enter
        page.goto(AMAZON_BASE, wait_until="domcontentloaded", timeout=30000)
        input("\n  [ACTION] Log in to Amazon in the browser if needed, then press Enter to continue... ")
        print("  Continuing...\n")

        try:
            result = _run(page, code, asin)
        except PlaywrightTimeoutError as exc:
            result = {"valid": False, "message": f"Timeout: {exc}"}
        except Exception as exc:
            result = {"valid": False, "message": f"Error: {exc}"}
        finally:
            context.close()

    return {"code": code, **result}


def _run(page, code: str, asin: str) -> dict:

    # ── Step 2 & 3: Add to cart directly via URL, then go to cart view ─────────
    print("  [2] Adding to cart directly...")
    page.goto(f"{AMAZON_BASE}/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1", wait_until="domcontentloaded", timeout=30000)

    print("  [3] Navigating to cart...")
    page.goto(f"{AMAZON_BASE}/gp/cart/view.html", wait_until="domcontentloaded", timeout=30000)

    # After clicking Add to Cart, navigate directly to cart — more reliable
    # than waiting for a confirmation popup (which varies by product)
    print("      Navigating to cart to confirm item added...")
    page.goto(f"{AMAZON_BASE}/cart", wait_until="domcontentloaded", timeout=30000)

    try:
        page.wait_for_selector(".sc-list-item", timeout=10000, state="visible")
        print("      Item confirmed in cart.")
    except PlaywrightTimeoutError:
        print("      Warning: could not confirm item in cart — proceeding anyway.")

    # ── Step 4: Proceed to Buy ───────────────────────────────────────────────
    print("  [4] Clicking Proceed to Buy...")
    proceed_btn = page.locator("input[name='proceedToRetailCheckout']").first
    proceed_btn.wait_for(state="visible", timeout=10000)
    proceed_btn.click()
    # Wait for checkout page to fully render — not just domcontentloaded
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    # Wait for the payment section to render (checkout uses JS pagelets)
    page.wait_for_selector('input[name="ppw-claimCode"]', timeout=20000, state="attached")
    print("      On checkout page.")

    # ── Step 5: Coupon input is already on the checkout page — no link needed ──
    print("  [5] Waiting for coupon input field...")
    page.wait_for_selector('input[name="ppw-claimCode"]', timeout=15000, state="visible")

    # ── Step 7: Fill coupon code ─────────────────────────────────────────────
    print(f"  [7] Filling code: {code}")
    code_input = page.locator('input[name="ppw-claimCode"]')
    code_input.click()
    code_input.select_text()
    code_input.type(code, delay=50)

    # ── Step 8: Click Apply ──────────────────────────────────────────────────
    print("  [8] Clicking Apply...")
    apply_btn = page.locator('input[name="ppw-claimCodeApplyPressed"]')
    apply_btn.scroll_into_view_if_needed()
    apply_btn.click(force=True)

    # ── Step 9: Wait for AJAX result to render ───────────────────────────────
    print("  [9] Waiting for result...")
    try:
        # Wait for error element to appear
        page.wait_for_selector(".pmts-error-message-inline", timeout=10000, state="attached")
    except PlaywrightTimeoutError:
        pass  # might be a success — fall through
    # Give AJAX a moment to fully update the DOM
    page.wait_for_load_state("domcontentloaded", timeout=10000)

    # ── Step 10 & 11: Parse result from body text ────────────────────────────
    body = page.inner_text("body")

    # Error — exact message confirmed from page inspection
    if "the promotional code you entered is not valid" in body.lower():
        return {"valid": False, "message": "The promotional code you entered is not valid."}

    # Other error keywords
    for kw in ["not valid", "invalid", "expired", "cannot be applied"]:
        if kw in body.lower():
            return {"valid": False, "message": f"Coupon error: {kw}"}

    # Success — code appears on page alongside "Promotion applied"
    if code.upper() in body.upper() and "promotion applied" in body.lower():
        return {"valid": True, "message": "Promotion applied"}

    return {"valid": False, "message": "Could not determine result — check browser"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Amazon Coupon Verifier")
    parser.add_argument("--code", type=str, required=True, help="Coupon/promo code to verify")
    parser.add_argument("--asin", type=str, default=ASIN, help=f"Amazon ASIN (default: {ASIN})")
    args = parser.parse_args()

    result = verify(args.code.strip().upper(), args.asin)
    print("\n" + "=" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 50)


if __name__ == "__main__":
    main()
