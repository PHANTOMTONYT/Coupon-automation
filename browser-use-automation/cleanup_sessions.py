"""
Stop all active Browser Use Cloud sessions.
Usage: python cleanup_sessions.py
"""

import asyncio
import os
from dotenv import load_dotenv
from browser_use_sdk import AsyncBrowserUse
from browser_use_sdk.types.session_update_action import SessionUpdateAction
load_dotenv()

API_KEY = os.getenv("BROWSER_USE_API_KEY") or os.getenv("BROWSER_USE", "")


async def cleanup():
    client = AsyncBrowserUse(api_key=API_KEY)
    sessions = await client.sessions.list_sessions(filter_by="active")
    items = getattr(sessions, "sessions", None) or getattr(sessions, "items", None) or []

    if not items:
        print("No active sessions found.")
        return

    print(f"Found {len(items)} active session(s). Stopping...")
    for s in items:
        await client.sessions.update_session(s.id, action=SessionUpdateAction.STOP)
        print(f"  Stopped: {s.id}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(cleanup())
