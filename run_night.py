import asyncio
import sys
from datetime import datetime

from src.night_shift import run_night_shift

if len(sys.argv) < 2:
    print("Usage: python run_night.py <day_session_id> [max_parallel]")
    sys.exit(1)

day_session_id = sys.argv[1]

max_parallel = 6
if len(sys.argv) >= 3:
    max_parallel = int(sys.argv[2])

now = datetime.now()
stamp = now.strftime("%H%M%S")
session_id = "night-" + stamp

print("Starting night shift")
print("day_session_id=", day_session_id)
print("session_id=", session_id)
print("max_parallel=", max_parallel)

asyncio.run(run_night_shift(day_session_id, session_id, max_parallel))
