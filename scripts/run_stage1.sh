#!/bin/bash
# run_stage1.sh
# 启动 Stage 1: Discovery (3 Agents Parallel)

set -e

TOPIC="${1:-diffusion models for time series}"

echo "🚀 Stage 1: Discovery"
echo "====================="
echo "Topic: $TOPIC"
echo ""

# 创建目录
mkdir -p .context/{stage1,stage2,stage3,stage4,checkpoints}
mkdir -p papers/{2024,2025}

# 检查 Zotero MCP
echo "📡 检查 Zotero MCP 连接..."
if claude mcp list 2>/dev/null | grep -q "zotero.*Connected"; then
    echo "  ✓ Zotero MCP 已连接"
else
    echo "  ⚠ Zotero MCP 未连接，继续执行 (Agent 将只使用外部搜索)"
fi
echo ""

# Agent 1-A: Paper Researcher
echo "📚 Agent 1-A: Paper Researcher (Claude Sonnet 4.6 + Zotero)"
echo "   任务: 深度分析 '$TOPIC' 相关论文"
echo "   - 检查 Zotero 中已有论文"
echo "   - 搜索 arXiv/Google Scholar/OpenReview"
echo "   - 将新发现存入 Zotero"
echo "   - 下载前 5 篇高相关 PDF"
echo ""

# 由于 conductor agent start 可能不可用，使用 Claude 直接执行
claude -c "
你现在是 Agent 1-A: Paper Researcher。

任务: 深度分析 '$TOPIC' 相关论文。

请执行以下步骤:
1. 使用 mcp__zotero__search_items 搜索 '$TOPIC' (如果可用)
2. 使用 WebSearch 搜索 arXiv 论文
3. 使用 WebSearch 搜索 Google Scholar
4. 整合结果，去重，选择最相关的 10 篇
5. 生成结构化报告

输出保存到: .context/stage1/papers_deep.md

报告结构:
# 论文深度分析报告: $TOPIC

## 1. Zotero 中已有的相关论文
[列出找到的论文]

## 2. 新发现的高相关论文
[列出外部搜索发现，带 arXiv 链接]

## 3. 研究地图 (关键方法分类)

## 4. 关键空白 (Gaps)

## 5. 推荐阅读顺序
" > .context/stage1/papers_deep.md 2>&1 &

AGENT1A_PID=$!
echo "   Agent 1-A PID: $AGENT1A_PID"
echo ""

# Agent 1-B: Code Scout
echo "💻 Agent 1-B: Code Scout (Claude Sonnet 4.6)"
echo "   任务: 搜索 '$TOPIC' 相关 GitHub 仓库"

claude -c "
你现在是 Agent 1-B: Code Scout。

任务: 搜索并分析 '$TOPIC' 相关 GitHub 仓库。

请执行:
1. 使用 WebSearch 搜索 GitHub 仓库
2. 分析前 10 个仓库的代码质量、活跃度
3. 评估可复用性

输出保存到: .context/stage1/code_analysis.md
" > .context/stage1/code_analysis.md 2>&1 &

AGENT1B_PID=$!
echo "   Agent 1-B PID: $AGENT1B_PID"
echo ""

# Agent 1-C: Web Scanner
echo "🌐 Agent 1-C: Web Scanner (Gemini 2.5 Pro)"
echo "   任务: 扫描 '$TOPIC' 技术博客和讨论"

# 注意：实际使用 Gemini 需要不同的调用方式
# 这里用 Claude 模拟
echo "   (注：实际应使用 Gemini 2.5 Pro)"

claude -c "
你现在是 Agent 1-C: Web Scanner。

任务: 扫描 '$TOPIC' 技术博客、论坛、教程。

请执行:
1. 搜索技术博客文章
2. 搜索开发者论坛讨论
3. 收集实践经验和痛点

输出保存到: .context/stage1/web_insights.md
" > .context/stage1/web_insights.md 2>&1 &

AGENT1C_PID=$!
echo "   Agent 1-C PID: $AGENT1C_PID"
echo ""

# 等待完成
echo "⏳ 等待所有 Agents 完成..."
echo "   (按 Ctrl+C 可以后台运行)"
wait $AGENT1A_PID
wait $AGENT1B_PID
wait $AGENT1C_PID

echo ""
echo "✅ Stage 1 完成！"
echo ""
echo "输出文件:"
echo "  - .context/stage1/papers_deep.md"
echo "  - .context/stage1/code_analysis.md"
echo "  - .context/stage1/web_insights.md"
echo ""
echo "下一步:"
echo "  1. 审核上述报告"
echo "  2. 创建 .context/checkpoints/checkpoint_1_response.md"
echo "  3. 运行 ./scripts/checkpoint_1.sh"
