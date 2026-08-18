# 墨阅 Markdown 阅读室

一个清爽、只读、零前端构建步骤的本地 Markdown 文档阅读器。

它把一个或多个文件夹中的 Markdown 文件组织成统一网页书架，提供来源切换、分级目录、跨库正文搜索、阅读状态记忆、实时刷新和可扩展主题中心。

适合集中查看 Codex、Claude Code 或其他 Agent 生成的大量 `.md` 文件，不需要移动原文件。

![墨阅界面预览](docs/preview.png)

## 主要功能

- 递归读取 `.md`、`.markdown`、`.mdown` 和 `.mkd`
- 同时挂载多个本地目录，按 Codex、Claude 等来源分组和筛选
- 用户不知道路径时，只读检查常见 Agent 目录并给出候选与参考位置
- 跨文档库搜索标题、路径和正文，也可只搜索当前来源
- 不同来源中的同名、同路径文件彼此隔离
- 左侧分级目录、最近阅读、收藏与折叠状态保存
- 右侧文章大纲与章节定位
- 每篇文档独立记忆阅读位置，重启浏览器后继续阅读
- 后台缓存目录与增量正文索引，文件变化后自动刷新
- 支持相对图片、内部 Markdown 链接、表格、任务列表和代码块
- 墨阅、GitHub、Notion、Codex、Claude 五种阅读风格
- 每种风格均支持浅色、深色和跟随系统，选择自动保存在浏览器中
- 主题在页面绘制前恢复，避免刷新时出现明暗闪烁
- 兼容手机和窄屏设备
- 浏览器端净化渲染结果，只读访问原始文档
- Python 标准库服务端，无需 Node.js 和前端构建工具

> GitHub、Notion、Codex 与 Claude 风格是针对阅读场景设计的主题灵感，并非对应产品的官方主题。

## 快速运行

要求 Python 3.10 或更高版本。

```bash
python assets/app/server.py --root "/path/to/markdown" --title "我的文档库" --open
```

直接启动多个目录：

```bash
python assets/app/server.py \
  --library "Codex=/path/to/codex-docs" \
  --library "Claude=/path/to/claude-docs" \
  --title "我的 Agent 文档书架" \
  --open
```

默认地址为 `http://127.0.0.1:4173`，仅当前电脑可以访问。

如果不确定 Markdown 文件位于哪里，可以先进行只读发现：

```bash
python scripts/discover.py
python scripts/discover.py --scan-root "/path/to/projects" --json
```

发现工具只检查常见 Agent 位置和用户指定的项目目录，不会自动添加来源，也不会扫描整块硬盘。

## 兼容 Agent Skill 部署

为兼容现有交付方式，仓库仍保留 Codex Skill。Agent 读取 `SKILL.md` 后，可以使用部署脚本生成独立运行目录：

如果用户不知道 Markdown 在哪里，先按上面的只读发现流程确认候选目录，再部署：

```bash
python scripts/deploy.py \
  --library "Codex=/path/to/codex-docs" \
  --library "Claude=/path/to/claude-docs" \
  --output "/path/to/markdown-reading-room" \
  --title "我的 Agent 文档书架"
```

单目录仍可继续使用旧参数 `--content "/path/to/markdown"`。更新现有安装时，只传 `--output` 会保留已经配置的全部来源。

部署后：

- Windows 双击 `start-reader.bat`
- macOS 或 Linux 运行 `./start-reader.sh`

## 项目结构

```text
serve-markdown-library/
├── README.md
├── CHANGELOG.md
├── ROADMAP.md
├── AGENTS.md
├── SKILL.md
├── agents/openai.yaml
├── assets/app/
│   ├── server.py
│   └── static/
├── scripts/
│   ├── discover.py
│   ├── deploy.py
│   └── build_release.py
├── tests/
└── .github/workflows/
```

## 开发与验证

项目仅依赖 Python 标准库。运行完整测试：

```bash
python -m unittest discover -s tests -v
python scripts/build_release.py
```

每次推送和 Pull Request 会在 Windows、macOS、Linux 上运行测试。推送 `v*` 标签后，GitHub Actions 自动生成并上传 Skill ZIP。

## 安全边界

- 默认只监听 `127.0.0.1`
- 服务只读取配置目录中的文件，不修改、移动或删除 Markdown
- 每个文档来源分别进行根目录边界校验，不能通过链接或路径跳到其他位置
- 忽略 `.git`、`.venv`、`node_modules` 等目录
- 资源接口限制可访问的文件类型和路径范围
- 当前版本不包含账号系统，不应直接暴露到公网

## 项目文档

- [CHANGELOG.md](CHANGELOG.md)：已经完成的版本变化
- [ROADMAP.md](ROADMAP.md)：方向性规划与候选版本，不代表固定排期
- [AGENTS.md](AGENTS.md)：代码贡献与验证规范

欢迎通过 Issue 提交使用场景和改进建议。
