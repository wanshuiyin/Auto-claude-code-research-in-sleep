/**
 * Optional executor-side scope limits.
 *
 * ARIS's reviewers already carry these limits — the block is embedded in the
 * skills that produce review prompts. Nothing bounds the executor the same way,
 * so this row offers the same contract as a system-prompt section. It is
 * disabled by default: it costs tokens on every request, and whether an
 * executor should be bound is a per-deployment choice.
 *
 * The text is read from the packaged `skills/shared-references/review-scope-limits.md`
 * rather than copied here, so the reviewer path and this one cannot drift apart.
 */

import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

export const name = 'aris-scope-limits'
export const inject = ['systemPrompt']

const DOCTRINE = fileURLToPath(
  new URL('../skills/shared-references/review-scope-limits.md', import.meta.url),
)

/** Prompt order: after the harness identity and persona, with tool guidance. */
const ORDER = 120

/** Reviewer-facing framing replaced by executor-facing framing, verbatim otherwise. */
const PREAMBLE = 'These limits bound what you PROPOSE and build, never what you look for.'

/**
 * Lift the canonical block out of the doctrine document.
 * @returns the fenced block's body, or undefined when the document has none.
 */
function extractBlock(markdown) {
  const fence = /```\n(=== SCOPE LIMITS[\s\S]*?)```/.exec(markdown)
  return fence === null ? undefined : fence[1].trim()
}

export async function apply(ctx) {
  const markdown = await readFile(DOCTRINE, 'utf8')
  const block = extractBlock(markdown)
  if (block === undefined) {
    throw new Error(`aris-scope-limits: no SCOPE LIMITS block in ${DOCTRINE}`)
  }
  ctx.effect(() => ctx.systemPrompt.section({
    name: 'aris:scope-limits',
    order: ORDER,
    text: `${PREAMBLE}\n\n${block}`,
  }), 'ARIS executor scope limits')
}
