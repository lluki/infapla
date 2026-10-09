import re
from typing import List, Dict, Any, Optional

CHECKBOX_PATTERN = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s*(.*)$")
PLAIN_BULLET_PATTERN = re.compile(r"^(\s*)[-*+]\s+(.*)$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")

def parse_todo_list(content: str) -> Dict[str, Any]:
    lines = content.splitlines()
    title = "TODO List"
    items = []
    item_counter = 0

    in_completed_section = False

    for idx, line in enumerate(lines):
        h_match = HEADING_PATTERN.match(line.strip())
        if h_match:
            level = len(h_match.group(1))
            name = h_match.group(2).strip()
            if level == 1:
                title = name
            elif name.lower() in ("completed", "done"):
                in_completed_section = True
            else:
                in_completed_section = False
            continue

        chk_match = CHECKBOX_PATTERN.match(line)
        if chk_match:
            item_counter += 1
            is_done = chk_match.group(2).lower() == 'x' or in_completed_section
            item_text = chk_match.group(3).strip()
            if item_text.startswith("~~") and item_text.endswith("~~") and len(item_text) > 4:
                item_text = item_text[2:-2].strip()

            items.append({
                "id": f"todo_{item_counter}",
                "text": item_text,
                "done": is_done,
                "raw_line": line,
                "line_index": idx
            })
            continue

        b_match = PLAIN_BULLET_PATTERN.match(line)
        if b_match and not line.strip().startswith("- ["):
            item_counter += 1
            item_text = b_match.group(2).strip()
            is_done = in_completed_section
            if item_text.startswith("~~") and item_text.endswith("~~") and len(item_text) > 4:
                item_text = item_text[2:-2].strip()
                is_done = True
            items.append({
                "id": f"todo_{item_counter}",
                "text": item_text,
                "done": is_done,
                "raw_line": line,
                "line_index": idx
            })

    active_items = [i for i in items if not i["done"]]
    done_items = [i for i in items if i["done"]]

    return {
        "title": title,
        "items": active_items + done_items,
        "active_count": len(active_items),
        "done_count": len(done_items)
    }

def format_todo_list(parsed: Dict[str, Any]) -> str:
    lines = [f"# {parsed.get('title', 'TODO List')}", ""]
    items = parsed.get("items", [])
    active_items = [i for i in items if not i.get("done")]
    done_items = [i for i in items if i.get("done")]

    for item in active_items:
        lines.append(f"- [ ] {item['text']}")
    
    if done_items:
        lines.append("")
        lines.append("## Completed")
        for item in done_items:
            lines.append(f"- [x] ~~{item['text']}~~")

    return "\n".join(lines).strip() + "\n"

def toggle_todo_item(content: str, item_id_or_text: str) -> str:
    parsed = parse_todo_list(content)
    target = item_id_or_text.strip().lower()

    for item in parsed["items"]:
        if item["id"] == item_id_or_text or item["text"].strip().lower() == target:
            item["done"] = not item["done"]
            break

    return format_todo_list(parsed)

def add_todo_item(content: str, text: str) -> str:
    parsed = parse_todo_list(content)
    new_item = {
        "id": f"todo_{len(parsed['items']) + 1}",
        "text": text.strip(),
        "done": False
    }
    active = [i for i in parsed["items"] if not i["done"]]
    done = [i for i in parsed["items"] if i["done"]]
    active.append(new_item)
    parsed["items"] = active + done
    return format_todo_list(parsed)

def remove_todo_item(content: str, item_id_or_text: str) -> str:
    parsed = parse_todo_list(content)
    target = item_id_or_text.strip().lower()
    parsed["items"] = [
        i for i in parsed["items"]
        if i["id"] != item_id_or_text and i["text"].strip().lower() != target
    ]
    return format_todo_list(parsed)
