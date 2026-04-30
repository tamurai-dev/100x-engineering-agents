---
name: invalid-tools-conflict
description: This agent has both tools and disallowedTools which are mutually exclusive.
model: sonnet
tools:
  - Read
  - Write
disallowedTools:
  - Bash
---

Both tools and disallowedTools specified.
