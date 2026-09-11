import json
import os


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _playbook_path():
    return os.path.join(_project_root(), "playbook.json")


def load_playbook():
    path = _playbook_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    lessons = []
    for item in data:
        text = str(item).strip()
        if text == "":
            continue
        lessons.append(text)
    return lessons


def save_playbook(lessons):
    path = _playbook_path()
    cleaned = []
    for item in lessons:
        text = str(item).strip()
        if text == "":
            continue
        cleaned.append(text)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2)
        f.write("\n")


def lessons_text(lessons):
    if lessons is None:
        return ""
    if len(lessons) == 0:
        return ""
    lines = []
    index = 1
    for lesson in lessons:
        text = str(lesson).strip()
        if text == "":
            continue
        lines.append(str(index) + ". " + text)
        index = index + 1
    if len(lines) == 0:
        return ""
    result = ""
    line_index = 0
    for line in lines:
        if line_index == 0:
            result = line
        else:
            result = result + "\n" + line
        line_index = line_index + 1
    return result
