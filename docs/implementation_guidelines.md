# OpAMP Coding and Implementation Guidelines

Use this file as the default implementation contract for contributors and coding agents.

## Scope and safety

- Keep changes focused: only modify files needed for the requested behavior.
- Do not revert or rewrite unrelated local changes.
- Avoid destructive repo commands unless explicitly requested.
- Preserve backwards compatibility unless the task explicitly approves a breaking change.

## Code standards

- Target Python `>=3.10`.
- Use descriptive names; avoid single-letter variable names.
- Include Apache 2.0 license header with `mp3monster.org` attribution in non-generated Python files.
- Add docstrings for public classes and methods, including purpose, inputs, and outputs. If a method implements an interface name the interface
- Prefer constants over repeated string literals and magic numbers.
- constants should have descriptive comments explaining what they represent
- Nested methods are discouraged
- Do not hand-edit generated protobuf artifacts unless regenerating them intentionally.
- code complexity should be restricted to a score of 15 unless this makes the code harder to follow
- maintain markdown files and diagrams so that they are instep with the code

## Project-specific rules

- Keep consumer/provider config behavior consistent with:
  - `OPAMP_CONFIG_PATH`
  - `config/opamp.json`
  - `consumer/opamp.json` and `tests/opamp.json` when applicable
- For `consumer/src`, avoid raw string-key literals where constants exist (enforced by hook).
- For OpAMP send/reporting logic, ensure resend cadence and flag updates are counted exactly once per successful send path.

## Testing requirements

- Add or update unit tests for every behavioral change.
- Minimum validation before handing off:
  - `pytest -q`
- For targeted changes, run impacted suites at minimum:
  - Consumer-only change: `pytest -q consumer/tests`
  - Provider-only change: `pytest -q provider/tests`
- If hooks are available, run:
  - `pre-commit run --files <changed-files>`
- implement tests to ensure that negative scenarios are safely handled

## Linting and formatting

- Run Ruff on changed files:
  - `ruff check --fix <paths>`
  - `ruff format <paths>`
- Keep diffs small and readable; avoid opportunistic refactors in bug-fix PRs.
- lines of code should not exceed 100 character wide

## PR/review checklist

- Behavior is correct for normal and error paths.
- New behavior is covered by tests.
- Logging remains useful but not noisy at default levels.
- Docs/config examples are updated when user-facing config/CLI changes.
- No duplicate side effects across layered methods (for example, counting/reporting done in both wrapper and callee).

## Reusable prompt block

Paste this into future coding requests:

```text
Follow docs/implementation_guidelines.md.
Only change files required for this task.
Preserve backwards compatibility unless I explicitly allow a breaking change.
Add/adjust tests for behavior changes and run the relevant pytest suites.
Run Ruff/pre-commit on changed files before finalizing.
```
