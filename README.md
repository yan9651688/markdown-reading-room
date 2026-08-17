# 墨阅 Markdown 阅读室

一个清爽、只读、零前端构建步骤的本地 Markdown 文档阅读器。

它把任意文件夹中的 Markdown 文件组织成网页文档库，提供分级目录、文章大纲、实时刷新和明暗主题。适合集中查看 Codex、Claude Code 或其他 Agent 生成的大量 `.md` 文件。

![墨阅界面预览](docs/preview.png)

## 主要功能

- 递归读取 `.md`、`.markdown`、`.mdown` 和 `.mkd`
- 左侧分级目录、文件名搜索与折叠状态保存
- 右侧文章大纲与章节定位
- Markdown 文件变化后自动刷新，并保留阅读位置
- 支持相对图片、内部 Markdown 链接、表格、任务列表和代码块
- 明亮与暗色主题，兼容手机和窄屏设备
- 浏览器端净化渲染结果，只读访问原始文档
- Python 标准库服务端，无需 Node.js 和前端构建工具

## 快速运行

要求 Python 3.10 或更高版本。

```bash
python assets/app/server.py --root "/path/to/markdown" --title "我的文档库" --open
```

默认地址为 `http://127.0.0.1:4173`，仅当前电脑可以访问。

## 作为 Agent Skill 部署

仓库本身同时是一个 Codex Skill。Agent 读取 `SKILL.md` 后，可以使用部署脚本为用户生成独立运行目录：

```bash
python scripts/deploy.py \
  --content "/path/to/markdown" \
  --output "/path/to/markdown-reading-room" \
  --title "项目文档库"
```

部署后：

- Windows 双击 `start-reader.bat`
- macOS 或 Linux 运行 `./start-reader.sh`

## 项目结构

```text
serve-markdown-library/
├── SKILL.md
├── agents/openai.yaml
├── assets/app/
│   ├── server.py
│   └── static/
├── scripts/deploy.py
└── scripts/build_release.py
```

## 安全边界

- 默认只监听 `127.0.0.1`
- 服务只读取配置目录中的文件，不修改、移动或删除 Markdown
- 忽略 `.git`、`.venv`、`node_modules` 等目录
- 资源接口限制可访问的文件类型和路径范围
- 当前版本不包含账号系统，不应直接暴露到公网

## 路线图

- 桌面端封装与系统托盘常驻
- PWA 与离线阅读
- iOS、Android 和平板适配
- 多目录书架与全文搜索
- 标签、收藏和最近阅读
- 远程同步、用户认证与团队共享
- 插件式 Markdown 扩展，例如 Mermaid、数学公式和脚注

欢迎通过 Issue 提交使用场景和改进建议。
