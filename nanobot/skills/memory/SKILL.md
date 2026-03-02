---
name: memory
description: Multi-file markdown memory system with contextual recall and scheduling.
always: true
---

# Memory

Your memory is a collection of markdown files in the `memory/` directory.
Every session, these files are loaded into your context automatically:
- `user.md` — user profile, preferences, core facts
- `schedule.md` — appointments, deadlines, recurring events
- `triggers.md` — context-triggered reminders (greetings, locations, activities)
- `INDEX.md` — catalogue of all memory files

Other files are loaded on demand via `read_file`.

## Memory Directory Layout

```
memory/
  user.md         # User profile — always in context
  schedule.md     # Calendar & commitments — always in context
  triggers.md     # Contextual recall triggers — always in context
  INDEX.md        # Catalogue of all files — always in context
  HISTORY.md      # Append-only event log — search with grep, never edit
  <topic>.md      # Agent-created topic files (you decide what to create)
  <subdir>/       # Optional subdirectories for topic clusters
```

## Contextual Recall (IMPORTANT)

On EVERY user message, check `triggers.md` (already in your context) for matching triggers:

**This is mandatory.** Before composing your response, scan `triggers.md` headings
against the user's message. If ANY trigger matches, read the referenced files FIRST,
then incorporate that information into your response.

- **Greetings** ("good morning", "hey", start of day): Show today's schedule, pending tasks, anything time-sensitive.
- **Locations** ("going to the grocery store", "heading to the city centre"): Surface relevant reminders, shopping lists, errands for that location.
- **Activities** ("let's work on X", "time to cook"): Load the relevant memory file and show current status.

When a trigger matches, proactively read the referenced files and include the relevant info in your response. Don't wait to be asked.

When adding new triggers, use descriptive headings and include example phrases:

```markdown
### Going Shopping
- Phrases: "heading to the store", "need groceries", "going to the supermarket"
- Check [[shopping.md]] and list what to buy
```

This helps match a wider range of synonyms and phrasings.

## Scheduling

`schedule.md` is your calendar. When the user mentions appointments, deadlines,
commitments, or recurring events, update it immediately:

- Use format: `- YYYY-MM-DD HH:MM — Description (details)`
- Keep `## Upcoming` sorted by date
- Move past events to `## Completed` periodically
- `## Recurring` for weekly/daily events: `- Monday 09:00 — Team standup`

When the user says good morning or asks about their day, check schedule.md
and proactively mention today's events and upcoming deadlines.

## Timezone

All times in `schedule.md` are in the user's timezone (from `user.md` -> `timezone`).
If the user's timezone is not set, ask them to provide it the first time they
mention a scheduled event.

## When to Write Memory

Write important facts immediately during the conversation, before responding:

- User preferences: "I prefer dark mode" → update `memory/user.md`
- Appointments: "I have a dentist on Friday at 3pm" → update `memory/schedule.md`
- Location reminders: "next time I'm at the mall, I need to return those shoes" → update `memory/triggers.md`
- Project context: "The API uses OAuth2" → write/update `memory/projects.md`
- Shopping: "I need to buy milk" → write/update `memory/shopping.md`
- Relationships: "Alice is the project lead" → write/update `memory/people.md`
- Standalone topics with many facts → create a new file

Do not wait for auto-consolidation. If the user tells you something, save it now.

## File Conventions

1. **Names**: `snake_case.md`, dates as `YYYY-MM-DD`
2. **Structure**: Start every file with `# Title`, sections with `## Section Name`
3. **Facts**: `- key: value` for discrete data, prose for narrative context
4. **Links**: `[[other_file.md]]` to reference another memory file
5. **Location**: All files under `memory/` — never elsewhere

## How to Write Memory

### Update an Existing File

```
read_file("memory/user.md")           # read current content
edit_file("memory/user.md", ...)      # apply targeted edit
```

Or use `write_file` when replacing the full file is simpler.

### Create a New File

Check `INDEX.md` (already in context) first to confirm no existing file covers this topic:

```
# 1. If no suitable file exists, create it:
write_file("memory/cooking.md", """# Cooking

## Dietary Preferences

- diet: vegetarian
- allergies: none

## Favourite Cuisines

- Italian, Japanese
""")
# 2. Update INDEX.md to include the new file:
edit_file("memory/INDEX.md", ...)
```

### Add a Cross-Reference

When `projects.md` mentions a person, link to `people.md`:

```markdown
## Acme Corp Redesign

Lead: [[people.md#alice]] — due 2026-06-01
```

## Searching Past Events

```bash
grep -i "keyword" memory/HISTORY.md
grep -iE "meeting|deadline" memory/HISTORY.md
```

Use the `exec` tool to run grep.

## Auto-Consolidation

Old conversations are automatically processed by a consolidation agent that
reads existing memory files, extracts new facts, and updates the relevant files.
INDEX.md is regenerated. You do not need to manage this — but don't rely on it
for important facts the user explicitly tells you. Save those immediately.
