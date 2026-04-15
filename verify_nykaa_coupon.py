"""
Nykaa Coupon Code Verifier
Usage:
  python verify_nykaa_coupon.py --code SAVE10
"""

import argparse
import json

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PRODUCT_URL      = "https://www.nykaa.com/dr-sheth-s-ceramide-vitamin-c-sunscreen/p/5237430"
NYKAA_HOME       = "https://www.nykaa.com"
PROFILE_DIR      = "nykaa_profile"
SELECTOR_TIMEOUT = 10000

# ---------------------------------------------------------------------------
# Verify coupon
# ---------------------------------------------------------------------------

def verify(code: str) -> dict:
    print(f"\nVerifying: {code!r}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = context.new_page()

        # Open Nykaa — user logs in if needed, then presses Enter
        page.goto(NYKAA_HOME, wait_until="domcontentloaded", timeout=30000)
        input("\n  [ACTION] Log in to Nykaa in the browser if needed, then press Enter to continue... ")
        print("  Continuing...\n")

        try:
            result = _run(page, code)
        except PlaywrightTimeoutError as exc:
            result = {"valid": False, "message": f"Timeout: {exc}"}
        except Exception as exc:
            result = {"valid": False, "message": f"Error: {exc}"}
        finally:
            context.close()

    return {"code": code, **result}


def _run(page, code: str) -> dict:

    # ── Step 2: Navigate to product page ────────────────────────────────────
    print("  [1] Navigating to product page...")
    page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=30000)

    # ── Step 3: Open bag sidebar ─────────────────────────────────────────────
    print("  [2] Opening bag sidebar...")
    page.wait_for_selector("button#header-bag-icon", timeout=SELECTOR_TIMEOUT)
    page.click("button#header-bag-icon")

    # ── Step 4: Wait for coupons section ─────────────────────────────────────
    print("  [3] Waiting for coupons section...")
    page.get_by_text("Apply now and save extra!").wait_for(timeout=SELECTOR_TIMEOUT)

    # ── Step 5: Click coupons section to open coupon page ────────────────────
    print("  [4] Opening coupons page...")
    page.get_by_text("Apply now and save extra!").click()
    page.wait_for_timeout(2000)

    # ── Step 6: Fill coupon code via JS (panel is open but not interactable) ─
    print(f"  [5] Filling code: {code}")
    filled = page.evaluate(f"""() => {{
        const input = document.querySelector('input.css-1vr4lgq');
        if (!input) return false;
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, '{code}');
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        input.focus();
        return true;
    }}""")
    if not filled:
        return {"valid": False, "message": "Could not find coupon input on page"}
    print(f"  [5] Input filled: {filled}")

    # ── Step 9: Click Collect (wait for button to be enabled) ───────────────
    print("  [8] Clicking Collect...")
    page.wait_for_selector("button.css-16s0jqs:not([disabled])", timeout=SELECTOR_TIMEOUT)
    page.click("button.css-16s0jqs")
    page.wait_for_load_state("networkidle")

    # ── Step 10/11: Check result ─────────────────────────────────────────────
    print("  [9] Reading result...")

    error_el = page.query_selector("div.css-94ukvu")
    if error_el:
        msg = error_el.inner_text().strip()
        return {"valid": False, "message": msg}

    success_el = page.query_selector("div.css-1ho2rs2")
    if success_el:
        msg = success_el.inner_text().strip()
        return {"valid": True, "message": msg}

    return {"valid": False, "message": "Could not determine result — check browser"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nykaa Coupon Verifier")
    parser.add_argument("--code", type=str, required=True, help="Coupon code to verify")
    args = parser.parse_args()

    result = verify(args.code.strip().upper())
    print("\n" + "=" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 50)


if __name__ == "__main__":
    main()
