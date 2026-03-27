# Zotero 配置指南 — MRI 运动伪影研究

> 本文档帮助你配置 Zotero MCP 服务器，使 ARIS 能够直接访问你的文献库。

---

## 为什么需要 Zotero？

### 优势
1. **你的标注 = 黄金数据** — Zotero 中高亮和笔记反映了你认为重要的内容
2. **自动去重** — 避免重复下载你已拥有的论文
3. **快速检索** — 无需等待 web 搜索，直接从本地库获取
4. **BibTeX 导出** — 为论文写作直接生成参考文献

### 场景
- 你已经在 Zotero 中收藏了 MRI/医学影像相关论文
- 你想基于已有知识库进行文献调研
- 你希望 ARIS 了解你关注的研究方向

---

## 安装步骤

### Step 1: 安装 Zotero

如果尚未安装：

```bash
# macOS
brew install --cask zotero

# Windows
# 下载安装包: https://www.zotero.org/download/

# Linux
# 下载 tarball: https://www.zotero.org/download/
```

### Step 2: 安装 Zotero MCP Server

Zotero MCP 允许 Claude 直接访问你的 Zotero 库。

#### 方式 A: 使用 smithery 安装（推荐）

```bash
# 安装 smithery CLI
npx -y @smithery/cli@latest install @konnigsgerg/zotero-mcp --client claude
```

#### 方式 B: 手动安装

1. 克隆 MCP 服务器：
```bash
git clone https://github.com/konnigsgerg/zotero-mcp.git
cd zotero-mcp
npm install
npm run build
```

2. 配置 Claude：
```bash
# 编辑或创建 Claude 配置文件
# macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
# Windows: %APPDATA%/Claude/claude_desktop_config.json
```

3. 添加 MCP 配置：
```json
{
  "mcpServers": {
    "zotero": {
      "command": "node",
      "args": ["/path/to/zotero-mcp/dist/index.js"],
      "env": {
        "ZOTERO_API_KEY": "your_api_key",
        "ZOTERO_USER_ID": "your_user_id",
        "ZOTERO_LIBRARY_TYPE": "user"
      }
    }
  }
}
```

### Step 3: 获取 Zotero API Key

1. 打开 Zotero → Preferences → Sync
2. 登录 Zotero 账户（如未登录）
3. 访问: https://www.zotero.org/settings/keys
4. 创建新 key：
   - Name: `Claude Research`
   - 权限: **Allow read access** ✅
   - 权限: **Allow library access** ✅
   - 权限: **Allow notes access** ✅ (推荐)
   - 权限: **Allow write access** ❌ (不需要)

5. 复制生成的 API Key

### Step 4: 获取 Zotero User ID

1. 访问: https://www.zotero.org/settings/keys
2. 页面顶部显示你的 **User ID** (数字)
3. 或者点击 "Show API Key" 查看包含 User ID 的信息

### Step 5: 配置环境变量

#### 方式 A: 直接配置在 Claude 中

将 API Key 和 User ID 填入 Step 2 的 JSON 配置中。

#### 方式 B: 使用环境变量文件

创建 `~/.zotero_mcp_env`：
```bash
ZOTERO_API_KEY=your_api_key_here
ZOTERO_USER_ID=your_user_id_here
ZOTERO_LIBRARY_TYPE=user
```

修改 MCP 配置：
```json
{
  "mcpServers": {
    "zotero": {
      "command": "node",
      "args": ["/path/to/zotero-mcp/dist/index.js"],
      "env": {
        "ZOTERO_API_KEY": "${ZOTERO_API_KEY}",
        "ZOTERO_USER_ID": "${ZOTERO_USER_ID}",
        "ZOTERO_LIBRARY_TYPE": "user"
      }
    }
  }
}
```

### Step 6: 验证配置

在 Claude Code 中测试：

```bash
# 列出你的 Zotero 集合
mcp__zotero__list_collections

# 搜索 MRI 相关文献
mcp__zotero__search_items — query "MRI motion artifact" — limit 10

# 获取最近添加的文献
mcp__zotero__get_recent_items — limit 5
```

如果以上命令返回结果，配置成功！

---

## 为 MRI 研究创建 Zotero 集合

建议在 Zotero 中创建以下集合结构：

```
MRI Motion Correction Research/
├── 📚 Literature Review/
│   ├── k-space Methods/
│   ├── Image Domain Methods/
│   ├── Deep Learning Approaches/
│   └── Traditional Methods/
├── 💡 Ideas & Notes/
│   ├── Research Questions/
│   └── Method Ideas/
├── 📊 Datasets/
│   ├── Public Datasets/
│   └── Synthetic Data/
└── 🎯 Target Venues/
    ├── MICCAI Papers/
    ├── MRM Papers/
    └── TMI Papers/
```

### 快速导入相关文献

1. 在 Zotero 中创建集合: `MRI Motion Correction Research/Literature Review`

2. 使用 Zotero Connector 浏览器插件导入：
   - 访问 Google Scholar: https://scholar.google.com
   - 搜索: `"MRI motion artifact correction" deep learning`
   - 点击 Zotero Connector 图标导入相关论文

3. 批量导入 arXiv 论文：
```bash
# 使用 arxiv_fetch.py 下载到本地
python3 tools/arxiv_fetch.py search "MRI motion correction" — max 20
# 然后拖入 Zotero
```

---

## 在 ARIS 中使用 Zotero

### 文献调研时

```bash
# 1. 仅搜索 Zotero（如果你有完善的文献库）
/research-lit "MRI motion artifact" — sources: zotero

# 2. Zotero + Web 搜索（推荐）
/research-lit "MRI motion artifact" — sources: zotero, web

# 3. 获取特定文献的标注
mcp__zotero__get_item_children — itemKey "ABC12345"
```

### 查看你的收藏

```bash
# 列出所有集合
mcp__zotero__list_collections

# 获取特定集合的文献
mcp__zotero__get_collection_items — collectionKey "XYZ789" — limit 25

# 搜索特定标签
mcp__zotero__search_items — tag "motion-correction" — limit 10
```

### 导出参考文献

```bash
# 导出 BibTeX（用于论文写作）
mcp__zotero__export_bibliography — format bibtex — outputPath references.bib

# 导出 APA 格式
mcp__zotero__export_bibliography — format bibliography — style apa — outputPath references.txt
```

---

## 故障排除

### 问题 1: "Zotero MCP not available"

**原因**: MCP 服务器未正确配置

**解决**:
1. 检查 Claude 配置文件中 MCP 部分
2. 确保 zotero-mcp 路径正确
3. 重启 Claude Code

### 问题 2: "API Key invalid"

**原因**: API Key 错误或权限不足

**解决**:
1. 重新生成 API Key: https://www.zotero.org/settings/keys
2. 确保勾选了 "Allow library access"
3. 更新配置文件中的 API Key

### 问题 3: 返回空结果

**原因**: Zotero 库为空或未同步

**解决**:
1. 打开 Zotero 客户端确认有文献
2. 检查 Zotero → Preferences → Sync → 已登录
3. 点击同步按钮强制同步

### 问题 4: 无法访问群组图书馆

**原因**: 默认配置只访问个人图书馆

**解决**:
修改 `ZOTERO_LIBRARY_TYPE` 和 `ZOTERO_GROUP_ID`:
```json
{
  "env": {
    "ZOTERO_API_KEY": "your_key",
    "ZOTERO_GROUP_ID": "1234567",
    "ZOTERO_LIBRARY_TYPE": "group"
  }
}
```

---

## 最佳实践

### 1. 同步策略
- 定期在 Zotero 客户端点击同步按钮
- 保持 Zotero 客户端运行（确保云端同步）

### 2. 标注习惯
- 阅读时用 Zotero PDF 阅读器高亮关键段落
- 添加笔记记录你的想法和疑问
- 使用标签分类（如 `key-paper`, `to-read`, `method-reference`）

### 3. 与 ARIS 配合
- 文献调研前，先在 Zotero 搜索确认你没有遗漏已读文献
- 利用 Zotero 标注指导 ARIS 关注重点
- 新发现的论文导入 Zotero，建立长期知识库

---

## 无 Zotero 的替代方案

如果你不想配置 Zotero，ARIS 仍然可以正常工作：

```bash
# 纯 Web 搜索（无需任何配置）
/research-lit "MRI motion artifact" — sources: web

# 本地 PDF + Web
/research-lit "MRI motion artifact" — sources: local, web
```

只是会失去：
- 你的历史收藏和标注
- 自动去重功能
- 快速本地检索

---

## 快速配置检查清单

- [ ] Zotero 客户端已安装并运行
- [ ] 已登录 Zotero 账户
- [ ] 已创建 API Key（只读权限）
- [ ] 已获取 User ID
- [ ] 已安装 zotero-mcp
- [ ] 已配置 Claude MCP
- [ ] 已测试连接成功
- [ ] （推荐）已创建 MRI 研究集合
- [ ] （推荐）已导入一些基础文献

---

## 下一步

配置完成后，回到 `WORKFLOW.md` 启动多 Agent 并行探索。

```bash
# 测试命令
mcp__zotero__search_items — query "MRI motion" — limit 5
```

如有问题，检查：
1. Zotero 客户端是否运行
2. API Key 是否正确
3. 网络连接是否正常
