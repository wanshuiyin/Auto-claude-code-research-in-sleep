#!/bin/bash
# verify_agents.sh
# 验证所有 Agent 配置是否正确

set -e

echo "========================================"
echo "  Agent 配置验证脚本"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 计数器
PASSED=0
FAILED=0

# 测试函数
run_test() {
    local name="$1"
    local command="$2"

    echo -n "Testing $name... "
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC}"
        ((FAILED++))
        return 1
    fi
}

# ===== 1. 环境检查 =====
echo "1. 环境检查"
echo "-----------"

run_test "目录结构" "test -d .context/stage1 && test -d .context/stage2 && test -d papers/2025"
run_test "Claude CLI" "which claude"
run_test "Node.js" "which node"
run_test "npx" "which npx"

echo ""
echo "注: Conductor 是 Mac app，无需 CLI"

echo ""

# ===== 2. Zotero MCP 检查 =====
echo "2. Zotero MCP 检查"
echo "------------------"

# 检查 MCP 配置
if claude mcp list 2>/dev/null | grep -q "zotero.*Connected"; then
    echo -e "Zotero MCP 连接: ${GREEN}✓${NC}"
    ((PASSED++))
else
    echo -e "Zotero MCP 连接: ${RED}✗ (请检查配置)${NC}"
    ((FAILED++))
fi

# 检查 API 凭证
if [ -n "$ZOTERO_API_KEY" ] && [ -n "$ZOTERO_USER_ID" ]; then
    echo -e "环境变量设置: ${GREEN}✓${NC}"
    ((PASSED++))
else
    echo -e "环境变量设置: ${YELLOW}⚠ (使用 ~/.claude/settings.json)${NC}"
fi

echo ""

# ===== 3. Agent 配置文件检查 =====
echo "3. Agent 配置验证"
echo "-----------------"

# 检查主文档
run_test "主文档存在" "test -f RESEARCH_WORKFLOW_GUIDE.md"

# 检查关键 Agent 定义
run_test "Agent 1-A 配置" "grep -q 'paper-researcher' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 1-B 配置" "grep -q 'code-scout' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 1-C 配置" "grep -q 'web-scanner' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 2-x 配置" "grep -q 'analyzer-A' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 3-A 配置" "grep -q 'creative-generator' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 3-B 配置" "grep -q 'constraint-generator' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 4-A 配置" "grep -q 'novelty-verifier' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 4-B 配置" "grep -q 'prototype-prover' RESEARCH_WORKFLOW_GUIDE.md"
run_test "Agent 5 配置" "grep -q 'report-compiler' RESEARCH_WORKFLOW_GUIDE.md"

echo ""

# ===== 4. 脚本检查 =====
echo "4. 启动脚本验证"
echo "---------------"

run_test "验证脚本" "test -f scripts/verify_agents.sh"
run_test "Stage 1 脚本" "test -f scripts/run_stage1.sh || test -f run_idea_discovery.sh"

echo ""

# ===== 5. 模型可用性检查 =====
echo "5. 模型可用性"
echo "-------------"

echo "需要的模型:"
echo "  - claude-sonnet-4.6 (Agent 1-A, 1-B, 4-B)"
echo "  - claude-opus-4.6 (Agent 3-B, 4-A, 5)"
echo "  - gemini-2.5-pro (Agent 1-C)"
echo "  - openai/gpt-5.4 (Agent 2-x, 3-A, 4-A Phase 2)"
echo ""
echo "注意: 模型检查需要在 Conductor 环境中验证"
echo ""

# ===== 6. Zotero API 测试 =====
echo "6. Zotero API 测试"
echo "------------------"

# 尝试直接调用 Zotero API
USER_ID=$(grep -o '"ZOTERO_USER_ID": "[0-9]*"' ~/.claude/settings.json 2>/dev/null | grep -o '[0-9]*' || echo "")
API_KEY=$(grep -o '"ZOTERO_API_KEY": "[^"]*"' ~/.claude/settings.json 2>/dev/null | grep -o '"[^"]*"$' | tr -d '"' || echo "")

if [ -n "$USER_ID" ] && [ -n "$API_KEY" ]; then
    if curl -s "https://api.zotero.org/users/$USER_ID/items?limit=1" \
         -H "Zotero-API-Key: $API_KEY" > /dev/null 2>&1; then
        echo -e "Zotero API 连接: ${GREEN}✓${NC}"
        ((PASSED++))
    else
        echo -e "Zotero API 连接: ${RED}✗ (请检查 API Key)${NC}"
        ((FAILED++))
    fi
else
    echo -e "Zotero API 凭证: ${YELLOW}⚠ (未在 settings.json 中找到)${NC}"
fi

echo ""

# ===== 7. 总结 =====
echo "========================================"
echo "  验证结果"
echo "========================================"
echo -e "通过: ${GREEN}$PASSED${NC}"
echo -e "失败: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}所有检查通过！可以开始运行 Workflow。${NC}"
    echo ""
    echo "下一步:"
    echo "  1. 设置研究主题: export TOPIC='your topic'"
    echo "  2. 运行 Stage 1: ./run_idea_discovery.sh"
    exit 0
else
    echo -e "${YELLOW}部分检查失败，请修复后重试。${NC}"
    exit 1
fi
