# Zotero 集成（可选）

> 🇬🇧 English: [ZOTERO.md](ZOTERO.md)
> 接入 [`/research-lit`](../../skills/research-lit/SKILL.md) 以及调用它的上游 skill（`/idea-discovery`、`/research-pipeline`）。

如果你用 [Zotero](https://www.zotero.org/) 管理论文，`/research-lit` 可以搜索你的文献库、读取标注/高亮、导出 BibTeX——全部在联网搜索**之前**完成。这能显著提升引用质量，因为文献检索从你已经审过的论文开始。

## 推荐的 MCP server

**[zotero-mcp](https://github.com/54yyyu/zotero-mcp)**（1.8k⭐，语义搜索 + PDF 标注 + BibTeX 导出）

```bash
# 安装
uv tool install zotero-mcp-server   # 或: pip install zotero-mcp-server

# 添加到 Claude Code（本地 API——需要 Zotero 桌面端运行）
claude mcp add zotero -s user -- zotero-mcp -e ZOTERO_LOCAL=true

# 或使用 Web API（不需要打开 Zotero）
claude mcp add zotero -s user -- zotero-mcp \
  -e ZOTERO_API_KEY=your_key -e ZOTERO_USER_ID=your_id
```

> API Key 在 https://www.zotero.org/settings/keys 获取

## 启用后 `/research-lit` 新增能力

- 🔍 按主题搜索 Zotero 库（含语义/向量搜索）
- 📂 浏览 Collections 和 Tags
- 📝 读取你的 PDF 标注和高亮（你**个人**认为重要的内容）
- 📄 导出 BibTeX 供论文写作直接使用

## 配置 Zotero 后 `/research-lit` 的搜索顺序

配置后默认顺序变成：

1. **Zotero**（你的文献库——最快、信号最强）
2. **Obsidian**（如果[也配置了](OBSIDIAN_CN.md)——你加工后的笔记）
3. **本地 PDF**（项目目录下的）
4. **网络搜索**（`web`，包括 arXiv 和 Google Scholar；包含在默认 `all` 中）
5. **显式启用的外部源**（`semantic-scholar`、`deepxiv`、`exa`、`gemini`、`openalex`；只有在 `— sources:` 中显式列出时才搜索）

可以用 `— sources: zotero, web` 或 `— sources: all` 覆盖默认。

## 不用 Zotero？

没配置时 `/research-lit` 自动跳过，用本地 PDF + 网络搜索。无报错无警告。

## Zotero + Obsidian 组合工作流

很多研究者用 Zotero 存论文、Obsidian 记笔记。两个集成可以同时工作——`/research-lit` 先查 Zotero（原始论文 + 标注），再查 Obsidian（加工后笔记），再查本地 PDF，最后搜网络。Obsidian 半边的配置见 [OBSIDIAN_CN.md](OBSIDIAN_CN.md)。

## 相关 skill

- [`/research-lit`](../../skills/research-lit/SKILL.md) —— 主要消费者
- [`/idea-discovery`](../../skills/idea-discovery/SKILL.md) —— 内部调用 `/research-lit`
- [`/research-pipeline`](../../skills/research-pipeline/SKILL.md) —— Workflow 1 + 2 + 3 端到端
