/**
 * The independent reviewer: ARIS's codex-exec bridge as the `codex` MCP server.
 *
 * codex-cli 0.154 removed `codex mcp-server`. The bridge shipped in this package
 * (mcp-servers/codex-exec/server.py) speaks the same contract over `codex exec`.
 * Its location is known only here — the declarative layer cannot find the
 * package — so this module resolves it and hands the rest of the row's config to
 * dsh's MCP client unchanged.
 */

import { fileURLToPath } from 'node:url'
import * as mcpClient from '@deepseek-ai/dsh-mcp-client'

export const name = 'aris-codex'

const BRIDGE = fileURLToPath(new URL('../mcp-servers/codex-exec/server.py', import.meta.url))

export async function apply(ctx, config) {
  await ctx.plugin(mcpClient, {
    ...config,
    transport: 'stdio',
    serverName: 'codex',
    command: 'python3',
    args: [BRIDGE],
  })
}
