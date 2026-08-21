/**
 * ARIS bundle adapter for DeepSeek Harness.
 *
 * Four effects, none of which the declarative layer can express:
 *   1. mount the packaged skill corpus from a path only this module can resolve
 *   2. publish the package root as ARIS_REPO so skills reach their helper scripts
 *   3. project Codex's threadId into model-visible content so codex-reply works
 *   4. serve the run-status view its read-only projection of the loop artifacts
 */

import { fileURLToPath } from 'node:url'
import * as skillFilesystem from '@deepseek-ai/dsh-skill-filesystem'
import { registerRunStatus } from './run-status.mjs'

export const name = 'aris-skills'
export const inject = ['skills', 'tools']

/** Package root; identical in a git checkout and under node_modules. */
const PACKAGE_ROOT = fileURLToPath(new URL('../', import.meta.url))
const SKILL_ROOT = fileURLToPath(new URL('../skills/', import.meta.url))

/** Codex MCP tools whose reply carries a continuation threadId. */
const CODEX_TOOLS = new Set(['mcp__codex__codex', 'mcp__codex__codex-reply'])

export async function apply(ctx) {
  // ARIS skills resolve shared helpers through $ARIS_REPO/tools
  // (skills/shared-references/integration-contract.md). An operator-set value wins.
  ctx.effect(() => {
    const inherited = process.env.ARIS_REPO
    if (inherited === undefined) process.env.ARIS_REPO = PACKAGE_ROOT
    return () => {
      if (inherited === undefined && process.env.ARIS_REPO === PACKAGE_ROOT) {
        delete process.env.ARIS_REPO
      }
    }
  }, 'ARIS package root')

  // Rank 600 (bundledSkillDir): a project or user skill of the same name wins.
  await ctx.plugin(skillFilesystem, {
    providerName: 'aris',
    includeDefaultRoots: false,
    bundledSkillDir: SKILL_ROOT,
    watch: false,
  })

  registerRunStatus(ctx)

  // dsh renders only an MCP result's `content` to the model, while Codex returns
  // threadId solely in `structuredContent`. Without this the model cannot continue
  // a review thread, which the hard-tier Debate Protocol requires.
  ctx.on('tools/post-execute', async (exec, result, next) => {
    const decision = await next()
    if (!CODEX_TOOLS.has(exec.name)) return decision
    if (result.isError || decision.kind !== 'accept') return decision
    if (Object.hasOwn(decision, 'value')) return decision

    const threadId = result.value?.structuredContent?.threadId
    if (typeof threadId !== 'string') return decision

    // Prefixed and labelled: a spilled or pruned result keeps its head, and the
    // reviewer's own prose is never mistaken for harness metadata. The trailing
    // blank line matters — text blocks reach the model joined with no separator.
    return {
      ...decision,
      content: [
        {
          type: 'text',
          text: `Codex continuation metadata (not part of the reviewer response): threadId=${threadId}\n\n`,
        },
        ...decision.content ?? result.content,
      ],
    }
  })
}
