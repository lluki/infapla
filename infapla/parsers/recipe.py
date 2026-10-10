import re
from typing import List, Dict, Any, Optional

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_ITEM_PATTERN = re.compile(r"^(\s*)[-*+]\s+(.*)$")
NUMBERED_ITEM_PATTERN = re.compile(r"^(\s*)\d+\.\s+(.*)$")

def parse_recipe(content: str) -> Dict[str, Any]:
    """
    Parses a markdown recipe into structured fields:
    - title
    - metadata (servings, prep_time, cook_time, etc.)
    - ingredients: list of {"text": "...", "clean_name": "..."}
    - instructions: list of step strings
    - raw_content
    """
    lines = content.splitlines()
    title = "Recipe"
    metadata: Dict[str, str] = {}
    ingredients: List[Dict[str, str]] = []
    instructions: List[str] = []
    current_section = "intro"

    for line in lines:
        stripped = line.strip()
        h_match = HEADING_PATTERN.match(stripped)
        if h_match:
            level = len(h_match.group(1))
            sec_name = h_match.group(2).strip()
            if level == 1:
                title = sec_name
            else:
                sec_lower = sec_name.lower()
                if "ingredient" in sec_lower:
                    current_section = "ingredients"
                elif any(k in sec_lower for k in ("instruction", "direction", "method", "step", "preparation")):
                    current_section = "instructions"
                elif any(k in sec_lower for k in ("info", "meta", "detail")):
                    current_section = "metadata"
                else:
                    current_section = sec_lower
            continue

        if not stripped:
            continue

        # Tolerant detection for plain headers without leading '#'
        plain_sec = stripped.rstrip(":").strip().lower()
        if plain_sec in ("ingredient", "ingredients"):
            current_section = "ingredients"
            continue
        elif any(plain_sec.startswith(k) for k in ("instruction", "direction", "method", "step", "preparation")):
            current_section = "instructions"
            continue
        elif plain_sec in ("info", "meta", "metadata", "details"):
            current_section = "metadata"
            continue

        if current_section == "intro":
            if title == "Recipe":
                title = stripped
                continue

        if current_section == "metadata":
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                k_clean = k.strip().lstrip("-*# ")
                metadata[k_clean] = v.strip()
        elif current_section == "ingredients":
            l_match = LIST_ITEM_PATTERN.match(line)
            raw_ing = l_match.group(2).strip() if l_match else stripped
            clean_name = re.sub(r"^\d+[\s\w./-]*\s+(of\s+)?", "", raw_ing).strip()
            ingredients.append({
                "text": raw_ing,
                "clean_name": clean_name or raw_ing
            })
        elif current_section == "instructions":
            n_match = NUMBERED_ITEM_PATTERN.match(line)
            l_match = LIST_ITEM_PATTERN.match(line)
            if n_match:
                instructions.append(n_match.group(2).strip())
            elif l_match:
                instructions.append(l_match.group(2).strip())
            else:
                instructions.append(stripped)

    return {
        "title": title,
        "metadata": metadata,
        "ingredients": ingredients,
        "instructions": instructions,
        "raw_content": content
    }

def format_recipe(title: str, ingredients: List[str], instructions: List[str], metadata: Optional[Dict[str, str]] = None) -> str:
    lines = [f"# {title}", ""]
    if metadata:
        lines.append("## Info")
        for k, v in metadata.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines.append("## Ingredients")
    for ing in ingredients:
        lines.append(f"- {ing}")
    lines.append("")

    lines.append("## Instructions")
    for i, step in enumerate(instructions, 1):
        lines.append(f"{i}. {step}")
    lines.append("")

    return "\n".join(lines).strip() + "\n"
