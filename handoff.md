# InFaPla Project Handoff

**Date**: October 11, 2026  
**Repository**: `InFaPla` (Intelligent Family Planner)  
**Branch**: `main`  
**Test Suite**: 39/39 Passing (`python3 -m unittest discover tests`)

---

## 1. Project Overview

**InFaPla** is a local-first, privacy-respecting, AI-assisted family planner. It operates directly over a Git-managed directory of Markdown files and iCalendar (`.ics`) schedules. It combines:
- A responsive, decluttered web application for desktop and mobile.
- A background Python daemon with automated periodic Git commits and synchronization.
- An isolated [Bubblewrap](https://github.com/containers/bubblewrap) sandbox running Google Antigravity (`agy`) with scoped filesystem access.
- An optional Telegram bot for processing family invites (screenshots to `.ics`), recipes, and natural language queries.

---

## 2. Architecture & Tech Stack

```
InFaPla/
├── data/                      # Dedicated family storage (Git repository)
│   ├── shopping/              # Shopping list, recipes/, mealplan/
│   ├── todo/                  # Tasks & family to-dos
│   ├── calendar/              # Family schedules (*.ics)
│   └── notes/                 # General family notes & markdown docs
├── infapla/
│   ├── daemon.py              # Central orchestrator coordinating git, web, & AI
│   ├── server.py              # Flask HTTP API & Jinja templates
│   ├── git_manager.py         # Git tracking, diffs, sync, & auto-commit loop
│   ├── sandbox.py             # Bubblewrap launcher & stdio NDJSON stream handler
│   ├── telegram_bot.py        # Telegram companion bot (long-polling)
│   ├── parsers/               # Domain parsers: shopping, recipe, todo, calendar, mealplan
│   ├── static/                # Vanilla JS (`app.js`), CSS (`app.css`), Diff2Html
│   └── templates/index.html   # Single-page web application
├── run-agy-sandboxed.sh       # Bwrap sandbox wrapper for `agy`
├── tests/                     # Unittest suite (API, parsers, git, telegram)
└── main.py                    # Application entry point
```

- **Backend**: Python 3.10+, Flask, standard library `subprocess`/`threading`.
- **Frontend**: Vanilla ES6+ (`App` namespace), modern CSS variables, `Diff2Html` for raw Git diff inspection.
- **AI Agent**: Google Antigravity CLI (`agy`) connected via standard input/output streaming NDJSON, defaulted to fast low-latency models (`gemini-3.8-flash-low` with minimal reasoning effort).

---

## 3. Current State & Recent Features

### A. Decluttered Web UI & Burger Menu
- **Responsive Burger Menu Drawer**:
  - Accessible via header button `☰` and editor toolbar `☰ Menu`.
  - **🤖 Open Assistant**: Top item. Opens the overview assistant or a dedicated modal assistant when viewing a file.
  - **View Mode Chooser**: "Interactive", "Visual", and "Raw" moved out of the editor content window into the burger menu. Opening a file automatically chooses Interactive if available (shopping, recipe, meal plan, todo, calendar), otherwise Visual.
  - **🗑️ Delete File**: Dedicated file removal action in the burger menu asking for confirmation before deleting via `/api/file/delete`.
  - **Navigation Shortcuts**: Quick jumps to Overview, Shopping List, Tasks, Calendar, and New File creation.
- **Decluttered File View**: Removed the embedded top assistant card and mode tabs from the file view layout, maximizing editor screen real estate.
- **Enhanced Toast Notifications**:
  - Strictly single active notification (clears existing toast before displaying the next).
  - Prominent sizing with comfortable padding, and full-width layout on mobile screens (`@media (max-width: 600px)`).
  - Clicking a recipe ingredient presents "Added to shopping list" with working **Go to list** and **Undo** buttons.
- **Unified Overview**: Overview features family summary cards (**Shopping**, **Tasks**, **Calendar**, **Recipes**), followed by Recent Changes (commits and per-file diffs) and Folders Overview.
- **Live FS Synchronization**: Filesystem and Git status are actively polled every 3 seconds and refreshed on window focus or AI completion.

### D. Special Interactive Modes
- **Shopping List (`shopping/list.md`) & Ultra-Fast Ingredient Picker**:
  - **Ingredient Picker Modal**: Clicking "+ Add Item" or the add input opens a modal dialog with an auto-focused search input on top.
  - **Zero-Latency Client-Side Filtering**: Suggestions pre-computed by the server via `GET /api/shopping/suggestions` (built and cached from all recipes in `shopping/recipes/*.md`, active list in `shopping/list.md`, and past archives in `shopping/list-archive/*.md`). Pre-fetched once on the client for instantaneous client-side autocomplete and search.
  - **Already On List Detection**: Items already present on the active shopping list are styled in *italics* with a distinct `(already on list)` tag and dimmed opacity. Clicking them remains functional and alerts the user.
  - **Flexible Submission**: Pressing Enter submits free text or the selected suggestion; clicking any suggestion inserts it via `/api/shopping/add`; pressing ESC, clicking ✕, or clicking the backdrop dismisses the modal.
  - **Interactive Checkboxes**: Auto-save on toggle; completed items move to a bottom completed group with strikethrough and a ` category: CAT` postfix, enabling items to return to their original category when unclicked.
  - **📦 Archive Shopping List** button calling `/api/shopping/archive` to archive the current list to `shopping/list-archive/YYYY-MM-DD.md` and replace `shopping/list.md` with a clean empty shopping list.
  - AI Assistant action shortcuts: "Group by categories" and "Merge duplicates".
- **Recipes (`shopping/recipes/*.md`)**:
  - Structured metadata tags, ingredient checklists, and step-by-step instructions.
  - Clickable ingredients and **+ Add All to Shopping List** shortcut.
- **Calendar (`calendar/*.ics`)**:
  - Chronological schedule cards with an "+ Add Event" modal to append `.ics` VEVENT blocks.

---

## 4. How to Run & Verify

### Start the Daemon and Web Server
```bash
python3 main.py --dir ./data --port 8080
```
Visit `http://localhost:8080` in your browser.

### Run the Test Suite
```bash
python3 -m unittest discover tests
```
*Current status: 39 tests passing.*

### Start with Telegram Bot (Optional)
```bash
export TELEGRAM_BOT_TOKEN="<your-bot-token>"
python3 main.py --dir ./data --port 8080 --telegram
```

---

## 5. Next Steps & Recommended Work

1. **Remote Git Sync**: Expand `/api/git/sync` to handle remote `git pull --rebase` and `git push` once upstream remotes are configured.
2. **Conflict Resolution UI**: Provide visual 3-way merge or notification cards if remote sync introduces merge conflicts.
3. **Multi-Calendar Support**: Add filtering/color-tagging across multiple `.ics` files in the `calendar/` directory.
