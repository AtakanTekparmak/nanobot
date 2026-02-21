# nanobot Skills

This directory contains built-in skills that extend nanobot's capabilities.

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

## Attribution

These skills are adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system.
The skill format and metadata structure follow OpenClaw's conventions to maintain compatibility.

## Available Skills

| Skill | Description |
|-------|-------------|
| `memory` | Manage long-term memory and history |
| `cron` | Schedule recurring tasks |
| `github` | Interact with GitHub using the `gh` CLI |
| `tmux` | Remote-control tmux sessions |
| `skill-creator` | Create new skills |