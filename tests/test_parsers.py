import unittest
import datetime
from infapla.parsers.shopping import (
    parse_shopping_list,
    format_shopping_list,
    toggle_shopping_item,
    add_shopping_item,
    remove_shopping_item,
    GROUP_CATEGORIES_PROMPT,
    MERGE_DUPLICATES_PROMPT
)
from infapla.parsers.recipe import parse_recipe, format_recipe
from infapla.parsers.todo import (
    parse_todo_list,
    format_todo_list,
    toggle_todo_item,
    add_todo_item,
    remove_todo_item
)
from infapla.parsers.mealplan import parse_mealplan
from infapla.parsers.calendar import (
    parse_ics_file,
    create_ics_event,
    parse_ics_datetime,
    unfold_ics_lines
)

class TestShoppingParser(unittest.TestCase):
    def setUp(self):
        self.sample_md = """# Shopping List

## Produce
- [ ] Apples
- [ ] Bananas

## Dairy
- [ ] Milk
- [x] ~~Butter~~

## Completed
- [x] ~~Bread~~
"""

    def test_parse_shopping_list(self):
        data = parse_shopping_list(self.sample_md)
        self.assertEqual(data["title"], "Shopping List")
        self.assertEqual(data["active_count"], 3)
        self.assertEqual(data["done_count"], 2)
        # Check active items are first
        self.assertFalse(data["items"][0]["done"])
        self.assertTrue(data["items"][-1]["done"])

    def test_toggle_shopping_item_to_done(self):
        # Toggle 'Apples' to done -> should move to bottom
        new_md = toggle_shopping_item(self.sample_md, "Apples")
        data = parse_shopping_list(new_md)
        self.assertEqual(data["active_count"], 2)
        self.assertEqual(data["done_count"], 3)
        # Verify done items are rendered at the bottom
        last_item = data["items"][-1]
        self.assertTrue(last_item["done"])
        self.assertIn("## Completed", new_md)
        self.assertIn("- [x] ~~Apples~~", new_md)

    def test_toggle_shopping_item_back_to_active(self):
        # Toggle 'Bread' from done to active
        new_md = toggle_shopping_item(self.sample_md, "Bread")
        data = parse_shopping_list(new_md)
        self.assertEqual(data["active_count"], 4)
        self.assertEqual(data["done_count"], 1)

    def test_add_and_remove_shopping_item(self):
        added = add_shopping_item(self.sample_md, "Orange Juice", "Beverages")
        data = parse_shopping_list(added)
        texts = [i["text"] for i in data["items"]]
        self.assertIn("Orange Juice", texts)

        removed = remove_shopping_item(added, "Orange Juice")
        data2 = parse_shopping_list(removed)
        texts2 = [i["text"] for i in data2["items"]]
        self.assertNotIn("Orange Juice", texts2)

    def test_prompts_defined(self):
        self.assertIn("supermarket categories", GROUP_CATEGORIES_PROMPT)
        self.assertIn("merge", MERGE_DUPLICATES_PROMPT.lower())

class TestRecipeParser(unittest.TestCase):
    def setUp(self):
        self.sample_recipe = """# Spaghetti Carbonara

## Info
- Servings: 4
- Prep time: 15 mins

## Ingredients
- 400g Spaghetti
- 150g Pancetta
- 4 large Eggs

## Instructions
1. Boil pasta in salted water.
2. Crisp pancetta in a pan.
3. Mix eggs and cheese, then toss with pasta.
"""

    def test_parse_recipe(self):
        data = parse_recipe(self.sample_recipe)
        self.assertEqual(data["title"], "Spaghetti Carbonara")
        self.assertEqual(data["metadata"]["Servings"], "4")
        self.assertEqual(len(data["ingredients"]), 3)
        self.assertEqual(data["ingredients"][0]["clean_name"], "Spaghetti")
        self.assertEqual(len(data["instructions"]), 3)

    def test_format_recipe(self):
        formatted = format_recipe(
            title="Pancakes",
            ingredients=["2 Eggs", "1 cup Milk"],
            instructions=["Mix ingredients", "Fry in butter"]
        )
        self.assertIn("# Pancakes", formatted)
        self.assertIn("## Ingredients", formatted)
        self.assertIn("- 2 Eggs", formatted)
        self.assertIn("1. Mix ingredients", formatted)

    def test_parse_recipe_tolerant(self):
        # Plain text without markdown symbols
        plain_recipe = """Fluffy Banana Pancakes

Info:
Servings: 4
Prep time: 10 mins

Ingredients:
2 ripe Bananas
2 Eggs
1 cup Flour

Instructions:
1. Mash bananas
2. Whisk eggs
"""
        data = parse_recipe(plain_recipe)
        self.assertEqual(data["title"], "Fluffy Banana Pancakes")
        self.assertEqual(data["metadata"]["Servings"], "4")
        self.assertEqual(len(data["ingredients"]), 3)
        self.assertEqual(data["ingredients"][0]["text"], "2 ripe Bananas")
        self.assertEqual(len(data["instructions"]), 2)

    def test_parse_categorized_recipe(self):
        cat_recipe = """# Palak Paneer

## Ingredients

### Spices & Seasonings
- 1/2 tsp cumin seeds
- 1/4 tsp turmeric powder
- Salt to taste

### Other Ingredients
- 1/3 cup onion (finely chopped, ~1 small onion)
- 200–250 g paneer (or tofu, cubed)

## Instructions
1. Sauté aromatics.
2. Add paneer and serve.
"""
        data = parse_recipe(cat_recipe)
        self.assertEqual(data["title"], "Palak Paneer")
        self.assertEqual(len(data["ingredients"]), 5)
        self.assertEqual(data["ingredients"][3]["text"], "1/3 cup onion (finely chopped, ~1 small onion)")
        self.assertEqual(data["ingredients"][3]["category"], "Other Ingredients")
        self.assertEqual(data["ingredients"][0]["category"], "Spices & Seasonings")

        self.assertEqual(len(data["ingredient_categories"]), 2)
        self.assertEqual(data["ingredient_categories"][0]["name"], "Spices & Seasonings")
        self.assertEqual(len(data["ingredient_categories"][0]["items"]), 3)
        self.assertEqual(data["ingredient_categories"][1]["name"], "Other Ingredients")
        self.assertEqual(len(data["ingredient_categories"][1]["items"]), 2)

class TestTodoParser(unittest.TestCase):
    def setUp(self):
        self.sample_todo = """# Family TODO List

- [ ] Book dentist
- [ ] Fix bike

## Completed
- [x] ~~Pay taxes~~
"""

    def test_parse_and_toggle_todo(self):
        data = parse_todo_list(self.sample_todo)
        self.assertEqual(data["active_count"], 2)
        self.assertEqual(data["done_count"], 1)

        # Toggle 'Book dentist'
        toggled = toggle_todo_item(self.sample_todo, "Book dentist")
        data2 = parse_todo_list(toggled)
        self.assertEqual(data2["active_count"], 1)
        self.assertEqual(data2["done_count"], 2)
        self.assertTrue(data2["items"][-1]["done"])

    def test_add_and_remove_todo(self):
        added = add_todo_item(self.sample_todo, "Buy gift")
        data = parse_todo_list(added)
        self.assertEqual(data["active_count"], 3)

        removed = remove_todo_item(added, "Buy gift")
        data2 = parse_todo_list(removed)
        self.assertEqual(data2["active_count"], 2)

class TestMealplanParser(unittest.TestCase):
    def test_parse_mealplan(self):
        sample = """# Weekly Meal Plan

## Monday
- [Spaghetti Carbonara](../recipes/spaghetti-carbonara.md) - Quick dinner

## Tuesday
- Vegetable Curry: Mild spices
"""
        data = parse_mealplan(sample)
        self.assertEqual(len(data["days"]), 2)
        mon = data["days"][0]
        self.assertEqual(mon["day"], "Monday")
        self.assertEqual(mon["meals"][0]["dish"], "Spaghetti Carbonara")
        self.assertEqual(mon["meals"][0]["recipe_link"], "../recipes/spaghetti-carbonara.md")
        self.assertEqual(mon["meals"][0]["hints"], "Quick dinner")

class TestCalendarParser(unittest.TestCase):
    def test_create_and_parse_ics(self):
        start = datetime.datetime(2026, 10, 15, 10, 30)
        end = datetime.datetime(2026, 10, 15, 11, 30)
        ics_text = create_ics_event(
            summary="Kids Swimming Class",
            dtstart=start,
            dtend=end,
            location="Downtown Pool",
            description="Bring towel and goggles"
        )
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("SUMMARY:Kids Swimming Class", ics_text)
        self.assertIn("DTSTART:20261015T103000", ics_text)

        events = parse_ics_file(ics_text, filename="test.ics")
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["summary"], "Kids Swimming Class")
        self.assertEqual(ev["location"], "Downtown Pool")
        self.assertEqual(ev["description"], "Bring towel and goggles")
        self.assertEqual(ev["start_str"], "2026-10-15 10:30")

    def test_unfold_ics_lines(self):
        folded = "DESCRIPTION:This is a very long line\n that was folded onto\n  multiple lines"
        unfolded = unfold_ics_lines(folded)
        self.assertEqual(len(unfolded), 1)
        self.assertEqual(unfolded[0], "DESCRIPTION:This is a very long linethat was folded onto multiple lines")

if __name__ == "__main__":
    unittest.main()
