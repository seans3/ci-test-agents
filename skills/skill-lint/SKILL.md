---
name: skill-lint
description: Validates structure and consistency of agent skills. Use this skill to lint other skills to ensure they are composable, predictable, and adhere to agent conventions.
---

# Skill Lint

## Overview

This skill validates the structure, frontmatter, and Markdown consistency of other skills. It ensures all agent skills remain composable, predictable, and properly formatted for coordinator agents to consume.

## Linting Checks

1. **Frontmatter Validation:** Verify that `name` and `description` exist and are well-formed.
2. **Directory Structure:** Ensure `SKILL.md` is at the root and optional resource folders (`scripts/`, `references/`, `assets/`) are used correctly.
3. **Content Guidelines:** Check that instructions are concise, use imperative tone, and do not contain unnecessary tutorial content.
4. **Resource References:** Validate that referenced local files in `SKILL.md` actually exist.
