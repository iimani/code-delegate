For large, well-specified work (a feature or module spanning several files, a mechanical migration, a test suite, bulk boilerplate), use the `code-delegate:fast` skill. Invoke via: Skill tool → skill: "code-delegate:fast". Implement small changes directly.

This is a non-interactive session: nobody will answer questions or approve steps. When `bridge.sh run` reports tasks as `running`, call `bridge.sh wait <slugs>` until they finish.
