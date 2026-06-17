---
name: skill-lint
description: Validates structure, frontmatter, and Markdown consistency of other agent skills. Use this skill when reviewing or finalizing a new skill to ensure it is composable, predictable, and adheres to strict agent conventions.
---

# Skill Lint

## Overview

Because agents rely on skills to execute autonomous debugging, the structure of these skills must be completely predictable. This skill provides the definitive linting rules that every other skill in this repository must pass.

## Linting Rules

### 1. File Structure
*   **Root Directory:** Every skill MUST exist in its own directory under `skills/` (e.g., `skills/my-skill/`).
*   **Mandatory File:** The directory MUST contain a `SKILL.md` file at its root.
*   **Optional Folders:** If the skill requires external resources, they MUST be placed in `scripts/`, `references/`, or `assets/`. No other root-level folders are permitted inside the skill directory.

### 2. Frontmatter Validation
The `SKILL.md` MUST begin with a YAML frontmatter block.
*   **`name` Field:** Must exist, be lowercase, and use hyphens instead of spaces. Must match the directory name.
*   **`description` Field:** Must be a single-line string. It MUST clearly state what the skill does AND when an agent should trigger it.

### 3. Content and Tone
*   **Conciseness:** Skills share the agent's context window. The content MUST be strictly procedural. Strip out conversational filler, introductions, and lengthy tutorials.
*   **Imperative Tone:** Instructions MUST be written as commands (e.g., "Run the script", "Extract the payload") rather than suggestions ("You could try to run the script").
*   **TODO Checks:** The file MUST NOT contain any unresolved `[TODO]` or placeholder text.

### 4. Link & Resource Validation
*   If the skill references an external file (e.g., a script in the `scripts/` directory), that file MUST exist.
*   If the skill claims to execute a command, provide the exact shell command or path to the script.

## Execution
To use this skill, the agent should read the target `SKILL.md` file, apply the four rules above, and propose direct edits to fix any violations before the skill is packaged.
