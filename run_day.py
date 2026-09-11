import asyncio
import sys
from datetime import datetime

from data.questions import QUESTIONS
from data.questions_day2 import QUESTIONS_DAY2
from src.day_shift import run_day_shift

questions_name = "day1"
skills_flag = "off"

args = sys.argv[1:]
i = 0
while i < len(args):
    arg = args[i]
    if arg == "--questions":
        i = i + 1
        if i < len(args):
            questions_name = args[i]
    else:
        if arg == "--skills":
            i = i + 1
            if i < len(args):
                skills_flag = args[i]
    i = i + 1

questions_name = questions_name.strip().lower()
skills_flag = skills_flag.strip().lower()

if questions_name == "day2":
    questions = QUESTIONS_DAY2
    day_number = 2
else:
    questions = QUESTIONS
    day_number = 1
    questions_name = "day1"

use_skills = False
if skills_flag == "on":
    use_skills = True
    skills_flag = "on"
else:
    use_skills = False
    skills_flag = "off"

now = datetime.now()
stamp = now.strftime("%H%M%S")
session_id = "day-" + stamp

print("Starting day shift")
print("session_id=", session_id)
print("questions=", questions_name)
print("skills=", skills_flag)
print("day_number=", day_number)

asyncio.run(run_day_shift(session_id, questions, use_skills, day_number))
