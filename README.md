# InFaPla (Intelligent Family Planner)

**InFaPla** is an AI-powered family planning tool organized around a Git-managed directory containing Markdown and iCalendar files. It features a responsive, mobile-optimized web interface, a background daemon with periodic Git auto-committing, an isolated Bubblewrap sandbox running Google Antigravity (`agy`) via stdio, and an optional Telegram companion bot.

---

## Key Features

### 1. Web Interface
- **Overview Dashboard**:
  - Chatbot interface for querying family data. Queries are delegated to the background daemon with access to the family directory.
  - Quick summary widgets for **Shopping**, **Tasks/TODO**, **Calendar**, and **Recipes**.
  - Real-time Git status (Synced vs. Uncommitted changes) and recent commit activity timeline.
  - File browser navigating the workspace.
- **Generic Markdown Viewer & Editor**:
  - **WYSIWYG / Preview Tab**: Rendered view active by default.
  - **RAW Editor Tab**: Full markdown editor.
  - **Embedded File AI Assistant**: When viewing any file, file location and contents are passed as context to the AI agent. If the AI modifies the file, the editor view automatically updates in real-time.
- **Specialized Interactive Views**:
  - 🛒 **Shopping List (`shopping/list.md`)**:
    - Interactive checkboxes: clicking an item marks it as done.
    - Completed items are immediately crossed through and rendered at the bottom under `## Completed`.
    - Quick add input.
    - Predefined AI actions:
      - **Group by categories**: Reorganizes items by supermarket sections (Produce, Dairy, Pantry, etc.).
      - **Merge duplicates**: Consolidates duplicate entries and combines quantities.
  - 🍲 **Recipes (`shopping/recipes/*.md`)**:
    - Formatted recipe cards with prep time, servings, ingredients, and step-by-step instructions.
    - Clickable ingredients: clicking any ingredient immediately adds it to `shopping/list.md`.
    - "Add All to Shopping List" shortcut.
  - 📋 **Meal Plan (`shopping/mealplan/*.md`)**:
    - Day-by-day weekly meal planner linking directly to recipes.
  - ✅ **Tasks / TODO Organizer (`todo/list.md`)**:
    - Clickable tasks with checkboxes; completed items are pushed to the bottom and crossed through.
  - 📅 **Calendar (`calendar/*.ics`)**:
    - Markdown viewer is disabled for this directory.
    - Displays a clean, chronological list of upcoming family events.
    - Modal to schedule and add new iCalendar (`.ics`) events.

### 2. Background Daemon & Bubblewrap Sandbox
- **Periodic Git Commits**: Automatically detects uncommitted changes in the family directory and commits them periodically (configurable interval, default: 30s).
- **Bubblewrap Agentic Sandbox**: Executes `agy` with **only read-write access to the dedicated Markdown directory** (`/` is mounted read-only).
- **Stdio Communication**: Interacts with `agy` using the streaming NDJSON protocol (`--input-format stream-json --output-format stream-json`).

### 3. Telegram Companion Bot
- Listens as a Telegram bot (via long-polling, no public webhook required).
- Supports key family workflows:
  - 📸 **Invite Screenshot**: Send a photo/screenshot of an invitation -> the agent extracts details and automatically creates an `.ics` entry in `calendar/`.
  - 🍲 **Recipe Link**: Send a recipe URL -> the agent scrapes and creates a formatted recipe under `shopping/recipes/`.
  - 💬 **Generic Questions**: Ask questions about shopping items, meal plans, or family schedule.
  - 🔄 **Commands**: `/shopping`, `/todo`, `/calendar`, and `/reset` to start a new session.

---

## Directory Structure

```
InFaPla/
├── data/                             # Default dedicated MD directory (Git managed)
│   ├── shopping/
│   │   ├── list.md                   # Shopping list with done items at bottom
│   │   ├── recipes/                  # Family recipes (*.md)
│   │   └── mealplan/                 # Weekly meal plans (*.md)
│   ├── todo/
│   │   └── list.md                   # Family task list with done items at bottom
│   ├── calendar/
│   │   └── family.ics                # Standard iCalendar files
│   └── README.md
├── infapla/
│   ├── config.py                     # Configuration loader
│   ├── daemon.py                     # Daemon coordinator
│   ├── git_manager.py                # Git operations and periodic committer
│   ├── sandbox.py                    # Sandboxed agy runner (bwrap)
│   ├── server.py                     # Web application & REST APIs
│   ├── storage.py                    # Workspace files & data access
│   ├── telegram_bot.py               # Telegram bot interface
│   ├── parsers/                      # Parsers for shopping, recipes, todo, calendar, mealplan
│   ├── static/                       # Mobile-optimized CSS and Vanilla JS
│   └── templates/                    # Jinja2 HTML templates
├── run-agy-sandboxed.sh              # Bubblewrap launcher for agy
├── tests/                            # Test suite
└── main.py                           # CLI entrypoint
```

---

## Quick Start

### 1. Run Web Interface & Daemon

```bash
python3 main.py --dir ./data --port 8080
```

Open `http://localhost:8080` in your browser.

### 2. Run with Telegram Bot

```bash
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
python3 main.py --dir ./data --port 8080
```

### 3. Running the Test Suite

```bash
python3 -m unittest discover tests
```
