# 产品定位与竞争策略

> 研究快照：2026-08-18。仅采用产品官网和官方文档，不把版本节奏视为承诺。

## 结论

墨阅不再以“另一个 Markdown 编辑器”为目标，而是成为**跨 Agent、本地优先的成果验收层**：自动收集散落在不同目录中的 Markdown 交付物，识别来源与变化，让用户完成阅读、验收和跟进。

这个切口避开成熟编辑能力的正面竞争。Typora 已经覆盖实时预览、文件树、大纲、全局搜索、主题和导出；Obsidian 的核心是以 vault、内部链接和图谱组织个人知识；VS Code 则同时具备 Markdown 编辑/预览，以及在 Agents 窗口内审阅单个工作区的 Agent 改动。[Typora 功能](https://typora.io/) · [Obsidian Graph view](https://obsidian.md/help/Plugins/Graph%2Bview) · [VS Code Markdown](https://code.visualstudio.com/docs/languages/markdown) · [VS Code Agents window](https://code.visualstudio.com/docs/agents/agents-window)

另一方面，Agent 产品正在把“监督与验收”变成核心工作流：Codex 支持并行任务、线程内审阅和自动化结果队列；GitHub 的 Agent 以 Pull Request 请求人工审阅。但这些能力主要服务各自生态内的任务或代码变更。[Codex app](https://openai.com/index/introducing-the-codex-app/) · [GitHub 第三方 Coding Agents](https://docs.github.com/en/copilot/concepts/agents/about-third-party-coding-agents)

因此墨阅的机会不是替代它们，而是补上一个空位：**不绑定 Agent、不绑定仓库、不要求导入的本地成果收件箱。**

## 差异化边界

| 产品类型 | 擅长解决 | 墨阅不与其竞争的部分 | 墨阅的独占心智 |
| --- | --- | --- | --- |
| Markdown 编辑器 | 写作、排版、导出 | 富文本编辑与格式工具 | Agent 写完后，到哪里统一验收 |
| 知识库 | 链接、标签、长期沉淀 | 双链和个人知识建模 | 多个 Agent 当天交付了什么 |
| IDE / Agent 客户端 | 运行任务、审阅代码 diff | 对话、代码执行与仓库操作 | 跨工具、跨目录的非代码成果审阅 |
| GitHub PR | 团队代码审核 | 云端代码协作 | 私密、本机、尚未进入 Git 的成果 |

## 壁垒路线

1. **成果收件箱（当前落地）**：来源识别、新增/更新感知、待处理/阅读中/需跟进/已确认；所有元数据仅保存在本机，不修改原文档。
2. **可追溯验收**：保留版本快照、渲染态差异、变更摘要和验收历史，回答“Agent 改了什么”。
3. **跨 Agent 交付协议**：用可选 sidecar manifest 描述任务、Agent、产物、引用和验收标准；无 manifest 时继续零配置识别。
4. **反馈闭环**：把“需跟进”的批注导出为各 Agent 可执行的任务，而不是在墨阅内再造聊天工具。
5. **团队化但仍本地优先**：可签名的只读审阅包、策略化目录与审计记录；账号和云同步保持可选。

## 产品纪律

- 默认只读，不接管、不移动、不重写用户文件。
- 先把“发现 → 阅读 → 验收 → 跟进”做深，再增加编辑功能。
- Agent 识别必须允许回退为普通本地来源，不能依赖某一家平台 API。
- 桌面端、网页端共享同一交互模型；平台差异收敛在扫描、监听和索引层。
