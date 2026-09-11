import asyncio
from datetime import datetime

from src.day_shift import run_day_shift

now = datetime.now()
stamp = now.strftime("%H%M%S")
session_id = "day-" + stamp

print("Starting day shift session_id=", session_id)
asyncio.run(run_day_shift(session_id))
