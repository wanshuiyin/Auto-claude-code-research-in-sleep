# Idea Candidates

## Candidate 1: Boundary-Aware vs Count-Only Summaries

- **Status**: selected
- **Why it matters**: isolates the information-loss problem with exact analysis
- **Feasibility**: immediate; exhaustive enumeration is trivial
- **Expected result**: count-only trends toward chance, boundary-aware stays perfect

## Candidate 2: Transition-Parity Feature as a Minimal Sufficient Statistic

- **Status**: backup
- **Why it matters**: reframes the same task using transition parity instead of endpoints
- **Feasibility**: immediate
- **Expected result**: even transition count exactly recovers the label

## Candidate 3: Label-Noise Robustness Study

- **Status**: optional extension
- **Why it matters**: shows whether the gap persists under controlled corruption
- **Feasibility**: easy but not needed for the core demo
- **Expected result**: boundary-aware remains best but no longer perfect
