---
name: drawio-modern-diagrams
description: 利用 draw.io 或 diagrams.net 生成、修改并质检多种现代风格的图示，支持按风格预设模板绘图，或根据用户提供的参考图片学习视觉风格后应用到新图中，输出 PNG 或 SVG，并在发现文字溢出、连线穿越、拥挤布局、过多箭头等问题时迭代修正。当用户要求“画 draw.io 图 / 画甘特图 / 路线图 / 架构图 / 流程图 / 网络拓扑图 / 按参考图风格重画 / 导出 PNG / 检查图是否美观”时使用。
---

# Drawio Modern Diagrams Skill

详细中文使用说明见 `USAGE.zh-CN.md`。

## Goal
给定用户的图示需求，完成以下闭环：
1) 产出或修改 `.drawio` 文件，
2) 先确定风格来源：风格预设模板，或用户参考图片，
2) 导出 PNG 供视觉检查，必要时同时导出 SVG，
3) 用脚本检查高概率布局问题，
4) 人工复看 PNG 是否存在溢出、交叉、对齐不稳、箭头过多等问题，
5) 继续修正，直到结构检查与视觉检查都通过。

## How to run
- 配置：查看本技能目录下 `config.json`，其中定义了 draw.io CLI 路径、输出目录、风格预设、模板路径和质检阈值。
- 先决定风格来源，优先级如下：
  - 用户明确指定的风格预设
  - 用户上传或提供路径的参考图片
  - 根据图类型自动选择默认预设
- 若需要查看可用风格预设：
  - `python3 scripts/drawio_skill.py list-profiles`
- 若需要查看某个风格预设的模板与视觉约束：
  - `python3 scripts/drawio_skill.py show-profile --preset minimal-topology`
- 若需要从预设模板新建图：
  - `python3 scripts/drawio_skill.py copy-template --preset minimal-topology --output outputs/demo/topology.drawio`
- 若只知道图类型，不想手选预设：
  - `python3 scripts/drawio_skill.py copy-template --diagram-type topology --output outputs/demo/topology.drawio`
- 若怀疑 `.drawio` 文件被误加了 Markdown 说明、YAML 头或代码围栏，可先运行：
  - `python3 scripts/drawio_skill.py sanitize-input --input outputs/demo/topology.drawio`
- 若希望直接执行导出并做 QA，优先运行：
  - `python3 scripts/drawio_skill.py render --input outputs/demo/topology.drawio --out-dir outputs/demo --strict`
- `render` 的执行顺序是：
  - 先识别当前主机平台是 macOS、Windows 还是 Linux
  - 先尝试直接调用 draw.io CLI
  - 若当前是 macOS，再尝试 `launchctl` 外部 helper 执行器
  - 若前两者都不可用，则进入 source-only 模式，只输出 `.drawio` 源文件并跳过 PNG / SVG 导出
- 若需要生成标准导出命令，先运行：
  - `python3 scripts/drawio_skill.py export-commands --input outputs/demo/topology.drawio --out-dir outputs/demo`
- `export-commands` 默认会按当前主机 shell 习惯输出：
  - Windows 默认输出 PowerShell 命令
  - macOS / Linux 默认输出 POSIX shell 命令
  - 若需要，可显式指定 `--shell powershell` 或 `--shell cmd`
- 然后按输出的命令直接执行 draw.io CLI：
  - `/opt/homebrew/bin/drawio -x -f png -o outputs/demo outputs/demo/topology.drawio`
  - `/opt/homebrew/bin/drawio -x -f svg -o outputs/demo outputs/demo/topology.drawio`
- macOS 上若当前环境受限，导致 draw.io CLI 不能被当前 Python 进程稳定拉起，`render` 会优先尝试 `launchctl` helper；若 helper 也不可用，再回退到 source-only 模式，而不是把这类环境问题误判成绘图失败。
- Windows 上若没有可运行的 draw.io CLI，也会自动走 source-only 模式；脚本还会额外探测 `Program Files`、`Program Files (x86)` 和 `LocalAppData` 下的常见安装路径。
- 完成导出后，运行 QA 汇总：
  - `python3 scripts/drawio_skill.py qa-report --input outputs/demo/topology.drawio --out-dir outputs/demo`
- 其中 `qa-report` 会：
  - 调用 `scripts/lint_drawio.py`
  - 逐页检查多页 `.drawio`
  - 检查 PNG 是否已导出且不比 `.drawio` 旧
  - 输出是否应继续修图

## Style selection
- 风格预设详情见 `references/style-profiles.md`。
- 若用户提供参考图片，只学习视觉语言，不照搬图片中的业务结构、文案和布局逻辑。
- 参考图片至少提取这些字段：背景色调、主辅色、节点形状、圆角半径、边框粗细、阴影强弱、连线样式、留白密度、文字密度。
- 学到的风格优先通过“选择最近的预设 + 覆盖差异项”来落地，避免每次从零发明样式。
- 若参考图片视觉上很好看，但不适合当前图类型，保留其配色和质感，重建更清晰的拓扑或流程结构。

## Working style
- 优先用分区、列、卡片、阶段带、对齐关系表达结构，非必要不用箭头。
- 保持现代、清新、留白充分的视觉风格。
- 默认从左到右组织阅读顺序。
- 文字不要靠缩小字号硬塞进图中，优先拆行、扩宽、增高、重排。
- 甘特图与路线图优先复用 `soft-modern`。
- 网络拓扑图优先复用 `minimal-topology`。
- 汇报型架构图优先复用 `executive-blueprint`。
- 更复杂的风格约束见 `references/style-rules.md`；风格模板和参考图匹配细则见 `references/style-profiles.md`。

## What to present to the user
1) 给出最终 `.drawio` 文件路径。
2) 若当前环境支持导出，给出 PNG 路径；若同时导出 SVG，也给出 SVG 路径。若处于 source-only 模式，要明确说明本次仅交付 `.drawio`。
3) 说明本次使用的是哪个风格预设，或说明风格来自哪张参考图片。
3) 总结本轮修正了哪些问题，例如：
   - 文本溢出
   - 连线穿越卡片
   - 元素越界
   - 箭头冗余
   - 卡片间距不一致
4) 若仍有风险，明确指出残留问题与建议下一步。

## Constraints (MUST)
- 非必要不要使用箭头。只有当因果、依赖、方向性不画箭头就会歧义时才允许保留。
- 每次较大修改后都要重新导出 PNG，并重新做 lint 与人工目检；若当前环境处于 source-only 模式，则明确说明人工 PNG 目检被跳过。
- source-only 模式不再天然视为 QA 通过；若请求的导出物缺失，或 PNG 目检图不存在 / 已过期，则 `should_fix` 必须保持为 `true`。
- 不能只依赖脚本结果；必须看 PNG 是否真的美观。
- 优先保留可编辑源文件 `.drawio`，不要只交付图片。
- `.drawio` 文件内容必须直接是 draw.io XML；不要在文件前后添加 YAML front matter、Markdown 标题、解释文字或代码围栏。
- 若用户给了现有 `.drawio` 文件，默认在其基础上修改，不随意新建另一份除非用户要求。
- 若用户给了参考图片，默认保留“风格”而不是“内容结构”；不要把参考图中的具体节点硬搬进新图。
