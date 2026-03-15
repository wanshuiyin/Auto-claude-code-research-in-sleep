# OSS Hardening Minimal Example

This folder contains a tiny input repository plus sample outputs for the first two hardening stages.

## Layout

- `repo/`: intentionally under-engineered example project
- `expected/OSS_AUDIT.md`: sample audit output
- `expected/OSS_PLAN.md`: sample planning output

## Suggested Demo

Run the new skills against the sample repo:

```text
/oss-audit "examples/oss-hardening-minimal/repo"
/oss-plan "examples/oss-hardening-minimal/repo"
```

The outputs do not need to match the sample word-for-word. The important part is the shape:

- the audit covers all seven categories and includes a path-level change list with `P0/P1/P2`
- the plan turns those findings into checklist items with purpose, change points, acceptance criteria, commands, and impact
