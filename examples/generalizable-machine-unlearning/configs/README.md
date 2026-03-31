# Config Layout

These files are the canonical source of truth for the implementation scaffold.

- `setup.json`: global experiment defaults
- `methods.json`: baseline method definitions
- `shift_families.json`: named target-shift families
- `forget_sets.json`: named forget-set constructions
- `run_matrix.json`: tracker-aligned run specifications for `R001-R012`

The starter scripts load these configs instead of hard-coding run details in multiple places.
