The infapla (intelligent family planner) is a planning tool based around AI and a simple directory contaiing mostly md files. that directory is GIT managed to track history etc.

It has webinterface and optional a chatbot companion app

Implement in a language of your choice, but not node / javascript

# Components
## Web Interface
A simple HTTP server that serves an overview, and has a generic file editor. It assumes the directory is git managed and uses git to show history, last edited files. 

The overview page shows: A chatbot interface for asking questions.
AI queries are delegated to the background daemon - the same interface The bot runs with access to the MD directory.

There are a few directories that have special meaning:

shopping/
calendar/
todo/

The webinterface has a generic MD viewer that allows wysywig editing, there is also a RAW tab, by default, the view mode with wysywyg rendering is active. a tab with an editor exists.

When files in a special folder are opened, another primary tab appears that renders a specific viewer / editor

The AI chatbox is also available on the MD files, if a prompt is given, the location of the MD file is always passed in the context. The editor view is updated if the AI agent updates the file

Make the userface pretty but simple and mobile optimized.


## Background daemon
Git commits are done periodically by this daemon

It has an agentic sandbox - it uses bubblewrap to run agy with only access to the dedicated MD directory.

The daemon communicates with the stdio mode of AGY (google antigravity) to handle requests.

## Telegram interface

The daemon listens as telegram bot interface. example usecases that should work:

* send screenshot of an invite, automatically create calendar entry

* Send link of a recipe automatically created  correctly formatted recipe entry.

* ask about generic contents

Offer at least a /reset command to start a new session


# Directory Structure

## Shopping 

shopping/list.md
shopping/recipes/name-of-dish.md - recipes contain both ingredients and cooking instructions.
shopping/mealplan/YYYY-MM-DD.md - Meal plan of a specific week. links to existing recipes with hints

If a recipe is opened, the ingredients can be clicked and are added to the shopping list.

If the shopping list is opened it displays items on the shopping list,  a click marks it as "done".

Done items are rendered at the bottom and marked as cross through.

There is a few buttons at the bottom of the AI prompt: 
* Group by categories which sends a predefined prompt to reorganize the shopping list by categories (group items which are usually close by each other in the supermarket)
* Merge duplicates


## TODO organizer

TODO/list.md

Displays a clickable todo list, as in hte shopping list, crossed of items are pushed to the bottom.

## Calendar

CALENDAR/ical files

this directory does not contain md files - the md viewer should not be active, instead a simple next events list should be displayed. the format of this directory should be 

Displays a clickable todo list, as in hte shopping list, crossed of items are pushed to the bottom.

