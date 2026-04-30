---
name: valid-full
description: Full subagent with all optional fields populated for validation testing.
model: sonnet
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
permissionMode: default
maxTurns: 30
skills:
  - test-skill
mcpServers:
  - my-server
memory: project
background: false
effort: high
isolation: worktree
initialPrompt: Start by analyzing the codebase
color: blue
---

Full subagent for testing all fields.
