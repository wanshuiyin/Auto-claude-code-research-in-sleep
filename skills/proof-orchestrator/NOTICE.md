# NOTICE — EtaSkill provenance

## EtaSkill proof skill suite

Upstream: <https://github.com/shenmuxing/EtaSkill> (licensed MPL-2.0 as a
repository). The upstream project is authored and solely owned by this
contribution's author, who — as the sole copyright holder — submits this
adapted material under this repository's MIT license. The MPL-2.0 text that
accompanied an earlier revision of this PR was removed for that reason: the
copyright holder is relicensing their own work, not redistributing a third
party's MPL-covered files.

The following material is adapted from EtaSkill commit
`f49ce5dd6b0bfb7565c35063e10aa1ac42a480e9`:

- this `skills/proof-orchestrator/` directory
- the matching `skills/skills-codex/proof-orchestrator/` directory
- the adversarial proof-audit rubric, DeepSeek reviewer routing, and audit
  output contract internalized in those directories

ARIS-specific integration changes include host-neutral executor wording, use of
the existing `llm-chat` MCP route, Codex same-family assurance labeling,
skill-catalog/install-group registration, and non-conflicting routing alongside
the existing `/proof-checker`.
