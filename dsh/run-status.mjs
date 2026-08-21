/**
 * Host half of the ARIS run-status view: one read-only RPC that projects the
 * loop's durable artifacts for the browser tab.
 *
 * The artifacts stay canonical. Nothing here caches, writes, or interprets
 * them beyond parsing REVIEW_STATE.json and stat-ing the files ARIS maintains.
 */

import { readdir, readFile, stat } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'

/** Channel the browser half calls. */
export const ARIS_RPC_CHANNEL = '/aris'

/**
 * Artifacts every auto-review-loop run maintains, relative to the workspace.
 * Stage outputs (plan, draft) vary by workflow and are deliberately absent.
 */
const ARTIFACTS = [
  'review-stage/REVIEW_STATE.json',
  'review-stage/AUTO_REVIEW.md',
  'review-stage/REVIEWER_MEMORY.md',
  'review-stage/ACQUITTAL_LOG.jsonl',
]

/** Fields the view reads; anything else in the state file is passed through untouched. */
const STATE_FILE = 'review-stage/REVIEW_STATE.json'
const REVIEW_LOG = 'review-stage/AUTO_REVIEW.md'

/**
 * The latest round's ranked criticisms, verbatim.
 *
 * Score and verdict already come from the state file, so only the criticisms
 * are lifted — they are what explains why the loop continued or stopped.
 * A log that does not carry the block yields nothing rather than a guess.
 *
 * @returns the criticism lines without their numbering, or undefined.
 */
async function readCriticisms(workspace) {
  let text
  try {
    text = await readFile(join(workspace, REVIEW_LOG), 'utf8')
  } catch {
    return undefined
  }
  const lines = text.split('\n')
  let start = -1
  for (const [index, line] of lines.entries()) {
    if (/^\s*-\s*Key criticisms/i.test(line)) start = index
  }
  if (start === -1) return undefined
  const items = []
  for (const line of lines.slice(start + 1)) {
    const item = /^\s+\d+\.\s+(.*\S)\s*$/.exec(line)
    if (item === null) break
    items.push(item[1])
  }
  return items.length > 0 ? items : undefined
}

/** @returns `{exists, mtime, size}` for one workspace-relative path. */
async function describe(workspace, relative) {
  try {
    const info = await stat(join(workspace, relative))
    return { path: relative, exists: true, mtime: info.mtimeMs, size: info.size }
  } catch {
    return { path: relative, exists: false }
  }
}

/** @returns the parsed state file, or an error string the view shows verbatim. */
async function readState(workspace) {
  let text
  try {
    text = await readFile(join(workspace, STATE_FILE), 'utf8')
  } catch {
    return { state: undefined, stateError: undefined }
  }
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { state: undefined, stateError: `${STATE_FILE} is not a JSON object` }
    }
    return { state: parsed, stateError: undefined }
  } catch (error) {
    return { state: undefined, stateError: `${STATE_FILE} is not valid JSON: ${error.message}` }
  }
}

/** Where `tools/run_state.py` persists a resumable pipeline run. */
const RUNS_DIR = '.aris/runs'

/**
 * Read the most recently updated pipeline run, if any.
 *
 * A phase's `status` separates what the executor claims from what an
 * independent reviewer accepted: only `accept()` writes `accepted`, and only
 * with a recorded reviewer and verdict id. A `done` phase that never reached
 * `accepted` is an unmet acceptance obligation, and the view says so.
 *
 * @returns the run, or undefined when this workspace has no resumable run.
 */
async function readPipeline(workspace) {
  let names
  try {
    names = await readdir(join(workspace, RUNS_DIR))
  } catch {
    return undefined
  }
  let newest
  for (const name of names) {
    if (!name.endsWith('.json')) continue
    const path = join(workspace, RUNS_DIR, name)
    let run
    try {
      run = JSON.parse(await readFile(path, 'utf8'))
    } catch {
      continue
    }
    if (typeof run !== 'object' || run === null || !Array.isArray(run.phases)) continue
    if (newest === undefined || String(run.updated ?? '') > String(newest.updated ?? '')) newest = run
  }
  if (newest === undefined) return undefined
  return {
    runId: newest.run_id,
    updated: newest.updated,
    executor: newest.executor_model,
    executorFamily: newest.executor_family,
    phases: newest.phases.map(entry => ({
      phase: entry.phase,
      status: entry.status,
      artifact: entry.artifact ?? undefined,
      reviewer: entry.reviewer ?? undefined,
      reviewerFamily: entry.reviewer_family ?? undefined,
      independence: entry.review_independence ?? undefined,
      verdictId: entry.verdict_id ?? undefined,
    })),
  }
}

/**
 * Register the run-status RPC when a browser connection exists.
 * Headless compositions have no `connection`, so the channel never mounts.
 * @param ctx - the ARIS plugin's context.
 */
export function registerRunStatus(ctx) {
  ctx.inject(['connection', 'sessions'], (scoped) => {
    scoped.effect(() => scoped.connection.rpc.handle(
      ARIS_RPC_CHANNEL,
      async (endpoint, payload) => {
        if (endpoint !== 'state') {
          return { ok: false, error: { code: 'UNKNOWN_ENDPOINT', message: `unknown ARIS endpoint "${endpoint}"` } }
        }
        const sessionId = typeof payload === 'object' && payload !== null ? payload.sessionId : undefined
        if (typeof sessionId !== 'string') {
          return { ok: false, error: { code: 'BAD_REQUEST', message: 'sessionId is required' } }
        }
        const workspace = scoped.sessions.get(sessionId)?.header?.cwd
        if (typeof workspace !== 'string' || !isAbsolute(workspace)) {
          return { ok: true, value: { workspace: undefined, artifacts: [] } }
        }
        const { state, stateError } = await readState(workspace)
        const pipeline = await readPipeline(workspace)
        const criticisms = await readCriticisms(workspace)
        const artifacts = await Promise.all(ARTIFACTS.map(relative => describe(workspace, relative)))
        return {
          ok: true,
          value: {
            workspace,
            ...state !== undefined ? { state } : {},
            ...stateError !== undefined ? { stateError } : {},
            ...pipeline !== undefined ? { pipeline } : {},
            ...criticisms !== undefined ? { criticisms } : {},
            artifacts,
            readAt: Date.now(),
          },
        }
      },
      { authority: 'loopback' },
    ), 'ARIS run-status RPC')
  })
}
