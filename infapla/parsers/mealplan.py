import re
from typing import List, Dict, Any, Optional

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_ITEM_PATTERN = re.compile(r"^(\s*)[-*+]\s+(.*)$")

DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def parse_mealplan(content: str) -> Dict[str, Any]:
    lines = content.splitlines()
    title = "Weekly Meal Plan"
    current_day = "General"
    days_dict: Dict[str, List[Dict[str, Any]]] = {}

    for line in lines:
        stripped = line.strip()
        h_match = HEADING_PATTERN.match(stripped)
        if h_match:
            level = len(h_match.group(1))
            sec_name = h_match.group(2).strip()
            if level == 1:
                title = sec_name
            else:
                current_day = sec_name
                if current_day not in days_dict:
                    days_dict[current_day] = []
            continue

        l_match = LIST_ITEM_PATTERN.match(line)
        if l_match:
            raw_text = l_match.group(2).strip()
            link_match = LINK_PATTERN.search(raw_text)
            recipe_name = raw_text
            recipe_link = None
            hints = ""

            if link_match:
                recipe_name = link_match.group(1).strip()
                recipe_link = link_match.group(2).strip()
                remainder = raw_text[link_match.end():].strip().lstrip("-: ")
                hints = remainder
            elif " - " in raw_text:
                parts = raw_text.split(" - ", 1)
                recipe_name = parts[0].strip()
                hints = parts[1].strip()
            elif ": " in raw_text:
                parts = raw_text.split(": ", 1)
                recipe_name = parts[0].strip()
                hints = parts[1].strip()

            if current_day not in days_dict:
                days_dict[current_day] = []

            days_dict[current_day].append({
                "dish": recipe_name,
                "recipe_link": recipe_link,
                "hints": hints,
                "raw": raw_text
            })

    days_list = []
    for day, meals in days_dict.items():
        days_list.append({
            "day": day,
            "meals": meals
        })

    return {
        "title": title,
        "days": days_list,
        "raw_content": content
    }
