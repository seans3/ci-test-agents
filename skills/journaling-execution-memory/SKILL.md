---
name: journaling-execution-memory
description: Records agent actions and findings during debugging. Use this skill to maintain a clear journal of the debugging process, preventing overcomplicated logic and providing an execution trace.
---

# Journaling & Execution Memory

## Overview

This skill provides a mechanism to record the agent's actions, hypotheses, and findings. It maintains a clear "journal" of the debugging process to prevent the agent from getting stuck in loops, repeating failed strategies, or executing brittle logic.

## Journaling Practices

1. **Log Hypotheses:** Before executing a complex command, write down the hypothesis.
2. **Record Findings:** Document the outcome of commands, especially when tests fail or errors occur.
3. **Track Dead Ends:** Clearly mark approaches that did not yield results to avoid repeating them.
4. **Final Synthesis:** Compile the running journal into a final bug report or post-mortem document.
