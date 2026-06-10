# Default Delegation Behavior — OVERRIDES ALL EXECUTION SKILLS

**This rule takes priority over superpowers execution skills** (executing-plans,
subagent-driven-development, and any other skill that writes code).

When you reach the implementation phase — whether driven by brainstorming, a direct
request, or any other trigger — follow this flow instead of writing code yourself or
running executing-plans:

1. **Classify each sub-task** using the Distribution Analysis criteria in the
   `delegate` skill. Produce a distribution summary (DELEGATE / IMPLEMENT
   DIRECTLY / ROUTE TO LARGER MODEL) and present it to the user for approval.
2. **Skip writing-plans / prose spec generation.** The `.local_task_<slug>.md` files
   you are about to write ARE the plan. Writing a prose spec first and then converting
   it to a task file wastes tokens — the spec is never passed to the delegate.
3. **After user approval:** write task files for delegated tasks, implement direct tasks
   yourself, and invoke the bridge.

Invoke the skill via: `Skill tool → skill: "delegate"`

The skill handles everything: distribution criteria, spec format, worktree isolation,
bridge invocation, test gates, and feedback loops. If a backend is not installed (bridge
exits with code 10), ask the user whether to try a different backend or proceed yourself.

**When NOT to delegate** (do it yourself without asking):
- One-line fixes, config edits, or single-field changes
- Exploratory reads, git operations, or reviews
- The user explicitly says "do it yourself" or "don't delegate"

**HARD RULE — never delegate regardless of complexity:**
- Auth logic, token/signature validation (JWT, OAuth, HMAC), cryptography, secret handling, or input validation at trust boundaries. Local models are not auditable and must not touch security-critical code.
