When you reach the implementation phase, invoke the `code-delegate:delegate` skill
instead of writing code yourself. Invoke via: Skill tool → skill: "code-delegate:delegate"

This is a non-interactive session: treat your distribution summary as approved as soon as you have written it, and proceed straight to dispatch. When a delegated task finishes, review its changes and merge its branch into the current branch.

Because nobody can resume this session later, never run `bridge.sh` in the background: run it in the foreground and wait for its result. To dispatch several tasks in parallel, start them in one shell command with `&` and finish it with `wait`.
