# InFaPla Project Handoff

**Date**: October 10, 2026  
**Repository**: `InFaPla` (Intelligent Family Planner)  
**Branch**: `main`  
**Test Suite**: 33/33 Passing (`python3 -m unittest discover tests`)

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

### A. Decluttered Web UI
- **Unified Overview**: Removed sidebar clutter; the home view features family summary cards (**Shopping**, **Tasks**, **Calendar**, **Recipes**), followed by:
  - **Recent Changes**: Displays recent commits with changed file lists and interactive per-file side-by-side raw Git diff modals.
  - **Uncommitted Changes**: Dynamic banner alerting to uncommitted file changes with a working **Sync** action (`/api/git/sync`).
  - **Folders Overview**: Clean directory tree with direct links to open any folder in full detail.
- **URL Routing & State Persistence**: Preserves navigation state on page reloads (`?file=<path>` and `?folder=<path>`).

### B. Clean Directory Explorer
- Dedicated vertical folder view listing subdirectories first, followed by files.
- Parent directory navigation (`..`) and "+ New File in Folder" inline creation modal.
- Free of excessive icons or card wrapping for maximum readability.

### C. Content Window Tab System
- Mode chooser tabs (`Interactive`, `Visual`, and `Raw`) are anchored directly to the content card header rather than floating in top toolbars.
- **Interactive**: Active by default on special file types (shopping, tasks, recipes, mealplan, calendar). Auto-saves state on interactive actions (e.g. checking off items).
- **Visual**: Rendered markdown view with an embedded "Save File" button.
- **Raw**: Plain-text markdown editor with an embedded "Save File" button.
- Clean labeling: Eliminated dynamic emojis in tab headers for a professional, consistent look. Extraneous tabs are automatically hidden in directory views.

### D. Special Interactive Modes
- **Shopping List (`shopping/list.md`)**:
  - Interactive checkboxes with auto-save; completed items move to a bottom completed group with strikethrough.
  - **🧹 Clear Checked Off** button calling `/api/shopping/clear-completed` to prune completed items cleanly.
  - AI Assistant action shortcuts: "Group by categories" and "Merge duplicates".
- **Recipes (`shopping/recipes/*.md`)**:
  - Structured metadata tags, ingredient checklists, and step-by-step instructions.
  - Clickable ingredients to add items to `shopping/list.md`.
  - **🛒 Add Ingredients to Shopping List** button invoking the AI assistant with direct file context.
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
*Current status: 33 tests passing.*

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
