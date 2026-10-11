import os
import shutil
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .parsers.shopping import parse_shopping_list, add_shopping_item, toggle_shopping_item, remove_shopping_item, clear_completed_items, build_ingredient_suggestions
from .parsers.recipe import parse_recipe
from .parsers.todo import parse_todo_list, add_todo_item, toggle_todo_item, remove_todo_item
from .parsers.calendar import parse_ics_file, create_ics_event, delete_ics_event
from .parsers.mealplan import parse_mealplan

class Storage:
    def __init__(self, data_dir: Path, timezone: str = "Europe/Zurich"):
        self.data_dir = Path(data_dir).resolve()
        self.timezone = timezone
        self._suggestions_cache = None
        self.ensure_initialized()

    def resolve_path(self, rel_path: str) -> Path:
        """
        Safely resolves a relative path within data_dir, preventing directory traversal.
        """
        # Normalize and strip leading slashes
        clean_rel = rel_path.strip().lstrip("/")
        resolved = (self.data_dir / clean_rel).resolve()
        try:
            resolved.relative_to(self.data_dir)
        except ValueError:
            raise PermissionError(f"Access denied: path '{rel_path}' is outside workspace")
        return resolved

    def ensure_initialized(self) -> None:
        """
        Initializes directory structure and default template files if needed.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "shopping" / "recipes").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "shopping" / "mealplan").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "shopping" / "list-archive").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "todo").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "calendar").mkdir(parents=True, exist_ok=True)

        # Default shopping list
        shop_file = self.data_dir / "shopping" / "list.md"
        if not shop_file.exists():
            shop_file.write_text(
                "# Family Shopping List\n\n"
                "## Produce\n"
                "- [ ] Fresh Basil\n"
                "- [ ] Garlic\n"
                "- [ ] Lemons\n\n"
                "## Dairy & Eggs\n"
                "- [ ] Whole Milk (1 Gallon)\n"
                "- [ ] Greek Yogurt\n"
                "- [ ] Eggs (1 Dozen)\n\n"
                "## Pantry\n"
                "- [ ] Olive Oil\n"
                "- [ ] Spaghetti Pasta\n\n"
                "## Completed\n"
                "- [x] ~~Sea Salt~~\n"
                "- [x] ~~Coffee beans~~\n"
            )

        # Default recipes
        carbonara_file = self.data_dir / "shopping" / "recipes" / "spaghetti-carbonara.md"
        if not carbonara_file.exists():
            carbonara_file.write_text(
                "# Spaghetti Carbonara\n\n"
                "## Info\n"
                "- Servings: 4\n"
                "- Prep time: 10 mins\n"
                "- Cook time: 15 mins\n\n"
                "## Ingredients\n"
                "- 400g Spaghetti\n"
                "- 150g Guanciale or Pancetta\n"
                "- 4 large Egg yolks\n"
                "- 100g Pecorino Romano cheese, grated\n"
                "- 1 tbsp Coarsely ground black pepper\n\n"
                "## Instructions\n"
                "1. Bring a large pot of salted water to boil. Cook spaghetti until al dente.\n"
                "2. While pasta cooks, fry guanciale in a large pan over medium heat until golden and crispy. Turn off heat.\n"
                "3. In a bowl, whisk egg yolks, grated Pecorino, and black pepper together into a thick paste.\n"
                "4. Transfer hot cooked pasta into the pan with guanciale and toss to coat with the fat.\n"
                "5. Quickly pour egg mixture into pasta, tossing vigorously to create a silky, glossy sauce (the residual heat cooks the eggs without scrambling).\n"
                "6. Serve immediately garnished with extra black pepper and Pecorino Romano.\n"
            )

        pancakes_file = self.data_dir / "shopping" / "recipes" / "banana-pancakes.md"
        if not pancakes_file.exists():
            pancakes_file.write_text(
                "# Fluffy Banana Pancakes\n\n"
                "## Info\n"
                "- Servings: 4\n"
                "- Prep time: 10 mins\n"
                "- Cook time: 15 mins\n\n"
                "## Ingredients\n"
                "- 2 ripe Bananas\n"
                "- 2 Eggs\n"
                "- 1 cup Flour\n"
                "- 3/4 cup Milk\n"
                "- 1 tsp Baking powder\n"
                "- 1 tbsp Butter for frying\n"
                "- Maple Syrup for serving\n\n"
                "## Instructions\n"
                "1. Mash the ripe bananas in a mixing bowl.\n"
                "2. Whisk in eggs and milk until combined.\n"
                "3. Fold in flour and baking powder until just combined (don't overmix).\n"
                "4. Heat butter in a skillet over medium heat. Pour 1/4 cup batter for each pancake.\n"
                "5. Cook until bubbles form on top, flip and cook until golden brown.\n"
                "6. Serve warm with maple syrup.\n"
            )

        # Default meal plan
        mealplan_file = self.data_dir / "shopping" / "mealplan" / "2026-10-12.md"
        if not mealplan_file.exists():
            mealplan_file.write_text(
                "# Weekly Meal Plan: Week of Oct 12, 2026\n\n"
                "## Monday\n"
                "- [Spaghetti Carbonara](../recipes/spaghetti-carbonara.md) - Quick family dinner, prep pancetta early\n\n"
                "## Tuesday\n"
                "- [Banana Pancakes](../recipes/banana-pancakes.md) - Fun breakfast-for-dinner\n\n"
                "## Wednesday\n"
                "- Lemon Herb Grilled Chicken - Serve with steamed greens\n\n"
                "## Thursday\n"
                "- Roasted Vegetable & Lentil Soup - Great for autumn evening\n\n"
                "## Friday\n"
                "- Homemade Pizza Night - Get kids to help with toppings\n\n"
                "## Saturday\n"
                "- Family BBQ Burgers - Outdoor dinner\n\n"
                "## Sunday\n"
                "- Sunday Roast with Roasted Potatoes & Carrots\n"
            )

        # Default TODO list
        todo_file = self.data_dir / "todo" / "list.md"
        if not todo_file.exists():
            todo_file.write_text(
                "# Family TODO List\n\n"
                "- [ ] Schedule dental checkup for kids\n"
                "- [ ] Fix dripping faucet in downstairs bathroom\n"
                "- [ ] Plan Leo's 7th birthday party\n"
                "- [ ] Water garden plants & check compost\n\n"
                "## Completed\n"
                "- [x] ~~Renew car insurance~~\n"
                "- [x] ~~Submit kindergarten enrollment form~~\n"
            )

        # Default Calendar ics
        cal_file = self.data_dir / "calendar" / "family.ics"
        if not cal_file.exists():
            today = datetime.datetime.now().date()
            dt1 = datetime.datetime(today.year, today.month, min(28, today.day), 14, 0)
            ics_data = create_ics_event(
                summary="Leo's Soccer Practice",
                dtstart=dt1,
                dtend=dt1 + datetime.timedelta(hours=1, minutes=30),
                location="Community Sports Park Field 3",
                description="Bring water bottle and shin guards."
            )
            cal_file.write_text(ics_data)

        # Default README
        readme_file = self.data_dir / "README.md"
        if not readme_file.exists():
            readme_file.write_text(
                "# InFaPla - Intelligent Family Planner\n\n"
                "Welcome to your family planning workspace!\n\n"
                "Special directories:\n"
                "- `shopping/`: Shopping list (`list.md`), recipes (`recipes/`), and weekly meal plans (`mealplan/`)\n"
                "- `todo/`: Family task list (`list.md`)\n"
                "- `calendar/`: Family calendar events in standard `.ics` format\n\n"
                "All files are Git-tracked and managed automatically by the InFaPla background daemon.\n"
            )

    def classify_file(self, rel_path: str) -> str:
        """
        Determines the specialized file category.
        """
        p = Path(rel_path.strip().lstrip("/"))
        p_str = p.as_posix().lower()

        if p_str in ("shopping/list.md", "shopping/list.markdown"):
            return "shopping"
        if p_str.startswith("shopping/recipes/") and p.suffix.lower() in (".md", ".markdown"):
            return "recipe"
        if p_str.startswith("shopping/mealplan/") and p.suffix.lower() in (".md", ".markdown"):
            return "mealplan"
        if p_str in ("todo/list.md", "todo/list.markdown"):
            return "todo"
        if p_str.startswith("calendar/") or p.suffix.lower() in (".ics", ".ical"):
            return "calendar"
        if p.suffix.lower() in (".md", ".markdown"):
            return "markdown"
        return "generic"

    def list_files(self) -> List[Dict[str, Any]]:
        """
        Lists all files in data_dir with metadata.
        """
        results = []
        for root, dirs, files in os.walk(self.data_dir):
            # Ignore .git and cache
            if ".git" in dirs:
                dirs.remove(".git")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")

            for file in sorted(files):
                full_p = Path(root) / file
                rel_p = full_p.relative_to(self.data_dir).as_posix()
                try:
                    stat = full_p.stat()
                    results.append({
                        "path": rel_p,
                        "name": file,
                        "size": stat.st_size,
                        "mtime": int(stat.st_mtime),
                        "type": self.classify_file(rel_p)
                    })
                except Exception:
                    pass
        return sorted(results, key=lambda x: x["path"])

    def read_file(self, rel_path: str) -> str:
        target = self.resolve_path(rel_path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {rel_path}")
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, rel_path: str, content: str) -> None:
        target = self.resolve_path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._suggestions_cache = None

    def delete_file(self, rel_path: str) -> bool:
        target = self.resolve_path(rel_path)
        if target.exists() and target.is_file():
            target.unlink()
            self._suggestions_cache = None
            return True
        return False

    # Specialized helpers
    def get_shopping_data(self) -> Dict[str, Any]:
        content = self.read_file("shopping/list.md")
        return parse_shopping_list(content)

    def toggle_shopping(self, item_id_or_text: str) -> Dict[str, Any]:
        content = self.read_file("shopping/list.md")
        new_content = toggle_shopping_item(content, item_id_or_text)
        self.write_file("shopping/list.md", new_content)
        return parse_shopping_list(new_content)

    def add_shopping(self, text: str, category: Optional[str] = None) -> Dict[str, Any]:
        content = self.read_file("shopping/list.md")
        new_content = add_shopping_item(content, text, category)
        self.write_file("shopping/list.md", new_content)
        return parse_shopping_list(new_content)

    def remove_shopping(self, item_id_or_text: str) -> Dict[str, Any]:
        content = self.read_file("shopping/list.md")
        new_content = remove_shopping_item(content, item_id_or_text)
        self.write_file("shopping/list.md", new_content)
        return parse_shopping_list(new_content)

    def clear_shopping_completed(self) -> Dict[str, Any]:
        content = self.read_file("shopping/list.md")
        new_content = clear_completed_items(content)
        self.write_file("shopping/list.md", new_content)
        return parse_shopping_list(new_content)

    def archive_shopping_list(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Moves shopping/list.md to shopping/list-archive/YYYY-MM-DD.md
        and replaces shopping/list.md with an empty shopping list.
        """
        content = ""
        try:
            content = self.read_file("shopping/list.md")
        except Exception:
            pass

        today = target_date or datetime.date.today().strftime("%Y-%m-%d")
        archive_dir = self.data_dir / "shopping" / "list-archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        archive_filename = f"{today}.md"
        rel_archive_path = f"shopping/list-archive/{archive_filename}"
        self.write_file(rel_archive_path, content if content.strip() else "# Family Shopping List\n")

        empty_list = "# Family Shopping List\n"
        self.write_file("shopping/list.md", empty_list)

        return {
            "archived_to": rel_archive_path,
            "shopping": parse_shopping_list(empty_list)
        }

    def get_shopping_suggestions(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Precomputes and caches a unique list of clean ingredient suggestions
        built from existing recipes (*.md) and shopping lists (active and archived).
        """
        if not force_refresh and self._suggestions_cache is not None:
            return self._suggestions_cache

        recipe_contents: List[str] = []
        recipe_dir = self.data_dir / "shopping" / "recipes"
        if recipe_dir.exists():
            for p in sorted(recipe_dir.iterdir()):
                if p.is_file() and p.suffix.lower() in (".md", ".markdown"):
                    try:
                        recipe_contents.append(p.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        pass

        shopping_contents: List[str] = []
        list_file = self.data_dir / "shopping" / "list.md"
        if list_file.exists():
            try:
                shopping_contents.append(list_file.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                pass

        archive_dir = self.data_dir / "shopping" / "list-archive"
        if archive_dir.exists():
            for p in sorted(archive_dir.iterdir()):
                if p.is_file() and p.suffix.lower() in (".md", ".markdown"):
                    try:
                        shopping_contents.append(p.read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        pass

        suggestions = build_ingredient_suggestions(recipe_contents, shopping_contents)
        self._suggestions_cache = suggestions
        return suggestions

    def get_recipe_data(self, rel_path: str) -> Dict[str, Any]:
        content = self.read_file(rel_path)
        data = parse_recipe(content)
        data["path"] = rel_path
        return data

    def get_mealplan_data(self, rel_path: str) -> Dict[str, Any]:
        content = self.read_file(rel_path)
        data = parse_mealplan(content)
        data["path"] = rel_path
        return data

    def get_todo_data(self) -> Dict[str, Any]:
        content = self.read_file("todo/list.md")
        return parse_todo_list(content)

    def toggle_todo(self, item_id_or_text: str) -> Dict[str, Any]:
        content = self.read_file("todo/list.md")
        new_content = toggle_todo_item(content, item_id_or_text)
        self.write_file("todo/list.md", new_content)
        return parse_todo_list(new_content)

    def add_todo(self, text: str) -> Dict[str, Any]:
        content = self.read_file("todo/list.md")
        new_content = add_todo_item(content, text)
        self.write_file("todo/list.md", new_content)
        return parse_todo_list(new_content)

    def remove_todo(self, item_id_or_text: str) -> Dict[str, Any]:
        content = self.read_file("todo/list.md")
        new_content = remove_todo_item(content, item_id_or_text)
        self.write_file("todo/list.md", new_content)
        return parse_todo_list(new_content)

    def get_calendar_events(self) -> List[Dict[str, Any]]:
        cal_dir = self.data_dir / "calendar"
        events = []
        if cal_dir.exists():
            for f in cal_dir.iterdir():
                if f.is_file() and f.suffix.lower() in (".ics", ".ical"):
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                        events.extend(parse_ics_file(content, filename=f.name, default_tz=self.timezone))
                    except Exception:
                        pass
        # Sort chronologically by start date
        def sort_key(ev):
            dt = ev.get("dtstart")
            if dt:
                # Make timezone-naive for comparison
                return dt.replace(tzinfo=None)
            return datetime.datetime.max
        events.sort(key=sort_key)
        return events

    def add_calendar_event(
        self,
        summary: str,
        dtstart: datetime.datetime,
        dtend: Optional[datetime.datetime] = None,
        location: str = "",
        description: str = "",
        filename: Optional[str] = None
    ) -> str:
        cal_dir = self.data_dir / "calendar"
        cal_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            slug = "".join(c if c.isalnum() else "-" for c in summary.lower()).strip("-")[:30]
            ts = dtstart.strftime("%Y%m%d")
            filename = f"{ts}-{slug or 'event'}.ics"

        target = cal_dir / filename
        ics_text = create_ics_event(
            summary=summary,
            dtstart=dtstart,
            dtend=dtend,
            location=location,
            description=description,
            tz_name=self.timezone
        )
        target.write_text(ics_text, encoding="utf-8")
        return filename

    def delete_calendar_event(
        self,
        uid: Optional[str] = None,
        filename: Optional[str] = None,
        summary: Optional[str] = None
    ) -> bool:
        cal_dir = self.data_dir / "calendar"
        if not cal_dir.exists():
            return False

        target_files = []
        if filename:
            clean_name = Path(filename).name
            target = cal_dir / clean_name
            if target.exists() and target.is_file():
                target_files.append(target)

        # Fallback to check all calendar files if not found in specified file or if no file specified
        all_cal_files = sorted([f for f in cal_dir.iterdir() if f.is_file() and f.suffix.lower() in (".ics", ".ical")])
        for f in all_cal_files:
            if f not in target_files:
                target_files.append(f)

        for f in target_files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                new_content, count = delete_ics_event(content, uid=uid, summary=summary, filename=f.name)
                if count > 0:
                    remaining_events = parse_ics_file(new_content, filename=f.name, default_tz=self.timezone)
                    rel_p = f"calendar/{f.name}"
                    if remaining_events or f.name == "family.ics":
                        self.write_file(rel_p, new_content)
                    else:
                        self.delete_file(rel_p)
                    return True
            except Exception:
                pass

        return False
