import re
from typing import List, Dict, Any, Optional, Tuple

GROUP_CATEGORIES_PROMPT = (
    "Please reorganize the shopping list in shopping/list.md by supermarket categories "
    "(such as Produce, Bakery, Dairy & Eggs, Meat & Seafood, Pantry, Frozen, Household) "
    "so that items usually close to each other in the supermarket are grouped together under "
    "markdown ## Category headings. Keep all items, preserve checkbox statuses, "
    "and ensure all completed items (- [x]) are placed at the very bottom under a '## Completed' section."
)

MERGE_DUPLICATES_PROMPT = (
    "Please merge any duplicate or overlapping items in the shopping list in shopping/list.md. "
    "Combine quantities (e.g. '2 apples' + '3 apples' -> '5 apples' or 'Milk' + 'Milk' -> '2x Milk'). "
    "Keep all unique items, preserve existing categories, and keep all completed items (- [x]) "
    "at the very bottom under a '## Completed' section."
)

CHECKBOX_PATTERN = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s*(.*)$")
PLAIN_BULLET_PATTERN = re.compile(r"^(\s*)[-*+]\s+(.*)$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")

def parse_shopping_list(content: str) -> Dict[str, Any]:
    """
    Parses shopping/list.md content into categories and items.
    Returns:
    {
        "title": "...",
        "items": [
            {"id": "...", "text": "...", "done": bool, "category": "...", "raw": "..."}
        ],
        "categories": ["Produce", "Dairy", ...]
    }
    """
    lines = content.splitlines()
    title = "Shopping List"
    current_category = "General"
    items = []
    categories = []
    item_counter = 0

    for idx, line in enumerate(lines):
        heading_match = HEADING_PATTERN.match(line.strip())
        if heading_match:
            level = len(heading_match.group(1))
            name = heading_match.group(2).strip()
            if level == 1:
                title = name
            else:
                current_category = name
                if current_category not in categories and current_category.lower() not in ("completed", "done"):
                    categories.append(current_category)
            continue

        chk_match = CHECKBOX_PATTERN.match(line)
        if chk_match:
            item_counter += 1
            is_done = chk_match.group(2).lower() == 'x'
            item_text = chk_match.group(3).strip()
            
            # Clean strike-through if present in markdown text
            display_text = item_text
            if " category: " in display_text:
                base_part, sep, cat_part = display_text.rpartition(" category: ")
                if base_part.startswith("~~") and base_part.endswith("~~") and len(base_part) > 4:
                    base_part = base_part[2:-2].strip()
                display_text = f"{base_part}{sep}{cat_part}"
            if display_text.startswith("~~") and display_text.endswith("~~") and len(display_text) > 4:
                display_text = display_text[2:-2].strip()

            saved_cat = None
            if is_done or current_category.lower() in ("completed", "done"):
                if " category: " in display_text:
                    base_text, _, saved_cat = display_text.rpartition(" category: ")
                    display_text = base_text.strip()
                    saved_cat = saved_cat.strip()
                cat = "Completed"
            else:
                if " category: " in display_text:
                    base_text, _, saved_cat = display_text.rpartition(" category: ")
                    display_text = base_text.strip()
                    if current_category.lower() in ("completed", "done", "general", "") and saved_cat:
                        current_category = saved_cat.strip()
                cat = current_category

            items.append({
                "id": f"item_{item_counter}",
                "text": display_text,
                "done": is_done,
                "category": cat,
                "saved_category": saved_cat,
                "raw_line": line,
                "line_index": idx
            })
            continue

        bullet_match = PLAIN_BULLET_PATTERN.match(line)
        if bullet_match and not line.strip().startswith("- ["):
            item_counter += 1
            item_text = bullet_match.group(2).strip()
            is_done = current_category.lower() in ("completed", "done")
            display_text = item_text
            if " category: " in display_text:
                base_part, sep, cat_part = display_text.rpartition(" category: ")
                if base_part.startswith("~~") and base_part.endswith("~~") and len(base_part) > 4:
                    base_part = base_part[2:-2].strip()
                display_text = f"{base_part}{sep}{cat_part}"
            if display_text.startswith("~~") and display_text.endswith("~~") and len(display_text) > 4:
                display_text = display_text[2:-2].strip()
                is_done = True

            saved_cat = None
            if is_done or current_category.lower() in ("completed", "done"):
                if " category: " in display_text:
                    base_text, _, saved_cat = display_text.rpartition(" category: ")
                    display_text = base_text.strip()
                    saved_cat = saved_cat.strip()
                cat = "Completed"
            else:
                if " category: " in display_text:
                    base_text, _, saved_cat = display_text.rpartition(" category: ")
                    display_text = base_text.strip()
                    if current_category.lower() in ("completed", "done", "general", "") and saved_cat:
                        current_category = saved_cat.strip()
                cat = current_category

            items.append({
                "id": f"item_{item_counter}",
                "text": display_text,
                "done": is_done,
                "category": cat,
                "saved_category": saved_cat,
                "raw_line": line,
                "line_index": idx
            })

    # Sort so done items are rendered at the bottom
    active_items = [i for i in items if not i["done"]]
    done_items = [i for i in items if i["done"]]

    return {
        "title": title,
        "items": active_items + done_items,
        "active_count": len(active_items),
        "done_count": len(done_items),
        "categories": categories
    }

def format_shopping_list(parsed: Dict[str, Any]) -> str:
    """
    Serializes items back to clean markdown with done items at the bottom.
    Preserves categories on completed items via ' category: CAT' postfix.
    """
    lines = [f"# {parsed.get('title', 'Shopping List')}", ""]
    
    items = parsed.get("items", [])
    active_items = [i for i in items if not i.get("done")]
    done_items = [i for i in items if i.get("done")]

    # Group active items by category
    category_order = []
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for item in active_items:
        cat = item.get("category", "General")
        if cat.lower() in ("completed", "done"):
            cat = item.get("saved_category") or "General"
            item["category"] = cat
        if cat not in by_category:
            by_category[cat] = []
            category_order.append(cat)
        by_category[cat].append(item)

    if len(category_order) == 1 and category_order[0] in ("General", ""):
        # Flat list
        for item in active_items:
            lines.append(f"- [ ] {item['text']}")
        lines.append("")
    else:
        for cat in category_order:
            lines.append(f"## {cat}")
            for item in by_category[cat]:
                lines.append(f"- [ ] {item['text']}")
            lines.append("")

    # Render done items at the bottom under Completed
    if done_items:
        lines.append("## Completed")
        for item in done_items:
            text = item.get("text", "").strip()
            saved_cat = item.get("saved_category")
            if saved_cat and saved_cat.lower() not in ("completed", "done"):
                if " category: " not in text:
                    text = f"{text} category: {saved_cat}"
            lines.append(f"- [x] ~~{text}~~")
        lines.append("")

    return "\n".join(lines).strip() + "\n"

def toggle_shopping_item(content: str, item_id_or_text: str) -> str:
    """
    Toggles the done state of an item and pushes done items to the bottom.
    When moving to completed, records ' category: CAT' in the markdown item.
    When unclicking, restores the item to CAT if ' category: ' is present.
    """
    parsed = parse_shopping_list(content)
    target = item_id_or_text.strip().lower()

    for item in parsed["items"]:
        item_text_lower = item["text"].strip().lower()
        full_text_lower = (
            f"{item['text']} category: {item.get('saved_category', '')}".strip().lower()
            if item.get("saved_category")
            else item_text_lower
        )
        base_text_lower = (
            item["text"].rpartition(" category: ")[0].strip().lower()
            if " category: " in item["text"]
            else item_text_lower
        )

        if (
            item["id"] == item_id_or_text
            or item_text_lower == target
            or full_text_lower == target
            or base_text_lower == target
        ):
            item["done"] = not item["done"]
            if item["done"]:
                prev_cat = item.get("category", "General")
                if prev_cat.lower() in ("completed", "done"):
                    prev_cat = item.get("saved_category") or "General"
                item["saved_category"] = prev_cat
                item["category"] = "Completed"
            else:
                restored_cat = item.get("saved_category")
                if not restored_cat and " category: " in item["text"]:
                    base_t, _, restored_cat = item["text"].rpartition(" category: ")
                    item["text"] = base_t.strip()
                if restored_cat and restored_cat.lower() not in ("completed", "done"):
                    item["category"] = restored_cat
                else:
                    item["category"] = "General"
                item["saved_category"] = None
            break

    return format_shopping_list(parsed)

def add_shopping_item(content: str, text: str, category: Optional[str] = None) -> str:
    """
    Adds a new item to the shopping list.
    """
    parsed = parse_shopping_list(content)
    cat = category.strip() if category and category.strip() else "General"
    new_item = {
        "id": f"item_{len(parsed['items']) + 1}",
        "text": text.strip(),
        "done": False,
        "category": cat
    }
    # Prepend or append to active items
    active = [i for i in parsed["items"] if not i["done"]]
    done = [i for i in parsed["items"] if i["done"]]
    active.append(new_item)
    parsed["items"] = active + done
    return format_shopping_list(parsed)

def remove_shopping_item(content: str, item_id_or_text: str) -> str:
    """
    Removes an item from the shopping list.
    """
    parsed = parse_shopping_list(content)
    target = item_id_or_text.strip().lower()
    parsed["items"] = [
        i for i in parsed["items"]
        if i["id"] != item_id_or_text
        and i["text"].strip().lower() != target
        and (
            f"{i['text']} category: {i.get('saved_category', '')}".strip().lower() != target
            if i.get("saved_category")
            else True
        )
    ]
    return format_shopping_list(parsed)

def clear_completed_items(content: str) -> str:
    """
    Removes all checked-off (done) items from the shopping list.
    """
    parsed = parse_shopping_list(content)
    parsed["items"] = [i for i in parsed["items"] if not i.get("done")]
    return format_shopping_list(parsed)


QUANTITY_PREFIX_REGEX = re.compile(
    r'^(?:(?:ca\.?|approx\.?|about|to)\s+)?'
    r'(?:'
        r'(?:\d+(?:[./\-\u2013\u2014]\d+)?(?:\s+to\s+\d+(?:[./\-\u2013\u2014]\d+)?)?|\b(?:a|an|one|two|three|ein|eine|einer|eines|etwas|some)\b)\s*'
        r'(?:[xX*]\s*)?'
        r'(?:g|kg|oz|lb|lbs|ml|l|cl|dl|tsp|tbsp|el|tl|cup|cups|pinch|pinches|prise|prisen|glas|gläser|stk|stk\.|stück|stücke|bunch|bunches|bund|clove|cloves|zehe|zehen|can|cans|dose|dosen|slice|slices|scheibe|scheiben|piece|pieces|bottle|bottles|flasche|flaschen|packung|packungen|becher|drop|drops|tropfen|inch|small|medium|large|große?|mittlere?|kleine?)\b\s*'
    r'|'
        r'\d+(?:[./\-\u2013\u2014]\d+)?\s*(?:[xX*]\s*)?'
    r')'
    r'(?:of\s+|von\s+|x\s+)?',
    re.IGNORECASE
)

def clean_ingredient_name(raw: str) -> str:
    """
    Strips leading quantities, units, bullet points, preparation parentheticals,
    and returns a clean, capitalized ingredient name.
    """
    if not raw:
        return ""
    s = raw.strip()
    s = re.sub(r'^[-*+]\s+(?:\[[ xX]\]\s*)?', '', s)
    s = re.sub(r'^~~(.*)~~$', r'\1', s).strip()
    if ' category: ' in s:
        s = s.rpartition(' category: ')[0].strip()
    cleaned = QUANTITY_PREFIX_REGEX.sub('', s).strip()
    if not cleaned:
        cleaned = s
    paren_match = re.search(r'\s*\([^)]*\)\s*$', cleaned)
    if paren_match and paren_match.start() > 0:
        base = cleaned[:paren_match.start()].strip()
        if len(base) >= 2:
            cleaned = base
    cleaned = re.sub(r',.*$', '', cleaned).strip(' .-\t')
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned

def build_ingredient_suggestions(
    recipe_contents: List[str],
    shopping_contents: List[str]
) -> List[Dict[str, Any]]:
    """
    Builds a unique list of known ingredients with clean names, categories, and occurrence counts
    from given recipe and shopping list markdown contents.
    """
    from .recipe import parse_recipe
    items_map: Dict[str, Dict[str, Any]] = {}

    # 1. Process recipes
    for content in recipe_contents:
        if not content or not content.strip():
            continue
        try:
            parsed = parse_recipe(content)
            for ing in parsed.get("ingredients", []):
                raw_text = ing.get("clean_name") or ing.get("text", "")
                name = clean_ingredient_name(raw_text)
                if not name or len(name) < 2:
                    continue
                cat = (ing.get("category") or "").strip()
                key = name.lower()
                if key not in items_map:
                    items_map[key] = {"name": name, "category": cat, "count": 0}
                items_map[key]["count"] += 1
                if cat and cat.lower() not in ("other ingredients", "general", ""):
                    items_map[key]["category"] = cat
        except Exception:
            pass

    # 2. Process shopping lists (active and archived)
    for content in shopping_contents:
        if not content or not content.strip():
            continue
        try:
            parsed = parse_shopping_list(content)
            for it in parsed.get("items", []):
                raw_text = it.get("text", "")
                name = clean_ingredient_name(raw_text)
                if not name or len(name) < 2:
                    continue
                cat = (it.get("saved_category") or it.get("category") or "").strip()
                if cat.lower() in ("completed", "done", "general"):
                    cat = ""
                key = name.lower()
                if key not in items_map:
                    items_map[key] = {"name": name, "category": cat, "count": 0}
                items_map[key]["count"] += 1
                if cat:
                    items_map[key]["category"] = cat
        except Exception:
            pass

    # Normalize categories: default empty or generic to 'General'
    for item in items_map.values():
        if not item["category"] or item["category"].lower() in ("other ingredients", "completed", "done"):
            item["category"] = "General"

    # Sort primarily by frequency (descending) and secondarily alphabetically by name
    return sorted(items_map.values(), key=lambda x: (-x["count"], x["name"].lower()))


