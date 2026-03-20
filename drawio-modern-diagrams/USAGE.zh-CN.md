# Draw.io Modern Diagrams Skill 使用说明

这份文档面向两个目标：

1. 让你快速知道这个 skill 适合做什么、不适合做什么。
2. 给出一套可以直接执行的使用流程，包括参考示范。

## 1. 这个 skill 是做什么的

`drawio-modern-diagrams` 用于生成、修改和质检 draw.io / diagrams.net 图示，重点不是“随便画一张图”，而是形成一条完整闭环：

1. 选择风格来源。
2. 产出或修改 `.drawio` 源文件。
3. 导出 PNG / SVG。
4. 跑结构检查。
5. 人工看 PNG，继续修正。
6. 交付 `.drawio` 和导出图。

它特别适合以下任务：

- 甘特图
- 路线图
- 流程图
- 网络拓扑图
- 方案架构图
- 参考某张图片的视觉风格重绘

它不擅长的事情：

- 自动凭空生成复杂业务内容
- 完全替代人工审美判断
- 仅靠脚本判断“图已经很好看”

## 2. skill 目录结构

当前 skill 的主要文件如下：

- `SKILL.md`
  说明 skill 的目标、执行要求和交付规范。
- `config.json`
  运行配置，包括 draw.io CLI 路径、默认输出目录、预设风格和质检阈值。
- `scripts/drawio_skill.py`
  命令行入口，用于列出预设、复制模板、生成导出命令、汇总 QA。
- `scripts/lint_drawio.py`
  结构检查脚本，用于发现文本溢出、过小字号、元素重叠、连线穿越、越界、箭头滥用等问题。
- `references/style-profiles.md`
  风格预设说明。
- `references/style-rules.md`
  风格和排版规则。
- `assets/*.drawio`
  内置模板。

## 3. 环境要求

从当前 `config.json` 看，这个 skill 默认依赖：

- `python3`
- draw.io CLI：优先探测 `runtime.drawio_candidates` 中的候选命令
- 当前主机平台会自动识别为 `macOS`、`Windows` 或 `Linux`

建议先确认这两个命令可用。

示例：

```bash
python3 --version
/opt/homebrew/bin/drawio --help
```

如果你的 draw.io 安装路径不同，优先修改 `config.json` 里的 `runtime.drawio_candidates` 和 `runtime.drawio_bin`。
Windows 还会额外探测 `runtime.windows_drawio_path_templates` 里定义的常见安装路径，例如：

- `%ProgramFiles%\draw.io\draw.io.exe`
- `%ProgramFiles%\diagrams.net\diagrams.net.exe`
- `%ProgramFiles(x86)%\draw.io\draw.io.exe`
- `%LocalAppData%\Programs\draw.io\draw.io.exe`
- `%LocalAppData%\Programs\diagrams.net\diagrams.net.exe`

如果你要调整 macOS 的外部执行器，还可以看 `runtime.helper_executor`。

## 4. 两种使用方式

### 方式 A：作为 Codex skill 直接调用

如果你是在 Codex 里使用它，直接在需求里点明：

```text
用 $drawio-modern-diagrams 画一张极简网络拓扑图，白底、少箭头、输出 drawio 和 PNG。
```

或者：

```text
用 $drawio-modern-diagrams 按我给的参考图风格重画一张路线图，保留风格，不照搬结构。
```

推荐把这些信息一次说清楚：

- 图类型：如 `topology`、`roadmap`、`architecture`
- 是否指定预设：如 `minimal-topology`
- 是否有参考图
- 输出要求：`.drawio`、PNG、SVG
- 是否已有源文件要修改

### 方式 B：直接运行脚本

这是最稳定、最容易复现的方式。你可以把它当成一个小型命令行工具来用。

## 5. 快速开始

### 第一步：查看有哪些风格预设

```bash
python3 scripts/drawio_skill.py list-profiles
```

当前可用预设：

- `soft-modern`
- `minimal-topology`
- `executive-blueprint`

### 第二步：查看某个预设的视觉合同

```bash
python3 scripts/drawio_skill.py show-profile --preset minimal-topology
```

这个命令会告诉你：

- 这个预设适合什么图
- 模板路径是什么
- 背景、颜色、节点形状、连线风格是什么
- 如果用户给了参考图，应该抽取哪些风格字段

### 第三步：复制模板，生成一个可编辑的 `.drawio`

手动指定预设：

```bash
python3 scripts/drawio_skill.py copy-template \
  --preset minimal-topology \
  --output outputs/demo/topology.drawio
```

只指定图类型，让脚本自动选择预设：

```bash
python3 scripts/drawio_skill.py copy-template \
  --diagram-type topology \
  --output outputs/demo/topology.drawio
```

### 第四步：在 draw.io / diagrams.net 中编辑这个 `.drawio`

这一步通常是人工完成。建议按以下原则编辑：

- 优先用卡片、分区、列和标题表示结构
- 非必要不要加箭头
- 文本不要强行缩小到不可读
- 尽量让阅读顺序保持从左到右
- `.drawio` 文件本体只能保留 draw.io XML，不要在文件前后包 Markdown 说明、YAML 头、代码围栏或别的解释文字

如果你怀疑文件已经被这类内容污染，可以先执行：

```bash
python3 scripts/drawio_skill.py sanitize-input \
  --input outputs/demo/topology.drawio
```

这个命令会：

- 自动去掉 draw.io XML 前后的非 XML 内容
- 在原文件旁边生成一个 `.pre-sanitize.bak` 备份
- 保留修复后的 `.drawio` 原路径，方便直接重新打开

### 第五步：优先使用 `render` 一步完成导出和 QA

```bash
python3 scripts/drawio_skill.py render \
  --input outputs/demo/topology.drawio \
  --out-dir outputs/demo \
  --strict
```

这个命令会：

- 先判断当前主机是 macOS、Windows 还是 Linux
- 先探测当前环境里是否有可直接运行的 draw.io CLI
- 如果直接 CLI 可运行，则直接导出
- 如果当前是 macOS 且直接 CLI 不可运行，则尝试 `launchctl` 外部 helper 执行器
- 如果前两者都不可运行，则自动切到 source-only 模式
- 自动补足 QA 目检所需的 PNG
- 跑 lint
- 逐页检查多页 `.drawio`
- 检查导出图是否比 `.drawio` 更新
- 输出是否还需要继续修图

source-only 模式下的行为：

- 不导出 PNG / SVG
- 仍然输出 `.drawio` 源文件路径
- 仍然执行 lint
- 如果你请求的导出物不存在，或 PNG 目检图不存在 / 已过期，`should_fix` 会保持为 `true`

这主要用于两类环境：

- Windows 上没有安装 draw.io CLI
- 受限环境下，macOS 当前 Python 进程不能稳定拉起 draw.io，但又没有可用 helper

### 第六步：如果你想手动拆分流程，再生成导出命令

```bash
python3 scripts/drawio_skill.py export-commands \
  --input outputs/demo/topology.drawio \
  --out-dir outputs/demo
```

默认会输出 PNG 和 SVG 的导出命令。
默认 shell 规则如下：

- Windows: 自动按 PowerShell 风格输出命令
- macOS / Linux: 自动按 POSIX shell 风格输出命令

如果当前环境里已经探测到 draw.io 命令，它会优先使用探测到的那一条。
如果你要强制生成别的 shell 风格命令，可以显式指定：

```bash
python3 scripts/drawio_skill.py export-commands \
  --input outputs/demo/topology.drawio \
  --out-dir outputs/demo \
  --shell powershell
```

或者：

```bash
python3 scripts/drawio_skill.py export-commands \
  --input outputs/demo/topology.drawio \
  --out-dir outputs/demo \
  --shell cmd
```

### 第七步：执行导出

macOS / Linux 常见示例：

```bash
/opt/homebrew/bin/drawio -x -f png -o outputs/demo outputs/demo/topology.drawio
/opt/homebrew/bin/drawio -x -f svg -o outputs/demo outputs/demo/topology.drawio
```

Windows PowerShell 常见示例：

```powershell
& 'C:\Program Files\draw.io\draw.io.exe' -x -f png -o 'outputs\demo' 'outputs\demo\topology.drawio'
& 'C:\Program Files\draw.io\draw.io.exe' -x -f svg -o 'outputs\demo' 'outputs\demo\topology.drawio'
```

Windows CMD 常见示例：

```cmd
"C:\Program Files\draw.io\draw.io.exe" -x -f png -o "outputs\demo" "outputs\demo\topology.drawio"
"C:\Program Files\draw.io\draw.io.exe" -x -f svg -o "outputs\demo" "outputs\demo\topology.drawio"
```

### 第八步：执行 QA 汇总

```bash
python3 scripts/drawio_skill.py qa-report \
  --input outputs/demo/topology.drawio \
  --out-dir outputs/demo
```

如果你希望 QA 同时要求 `png` 和 `svg` 都是最新的，可以显式指定：

```bash
python3 scripts/drawio_skill.py qa-report \
  --input outputs/demo/topology.drawio \
  --out-dir outputs/demo \
  --formats png,svg
```

如果你想在图还有问题时直接返回失败码，可以加：

```bash
python3 scripts/drawio_skill.py qa-report \
  --input outputs/demo/topology.drawio \
  --out-dir outputs/demo \
  --strict
```

## 6. 推荐工作流

每次都按下面这条线走，效率最高：

1. 先判断图类型。
2. 再决定风格来源。
   优先级是：用户明确指定预设 > 用户参考图 > 图类型默认预设。
3. 复制最接近的模板。
4. 在 `.drawio` 里完成内容编辑。
5. 优先跑 `render`。
6. 如果 render 自动切到了 source-only 模式，而你又确实需要 PNG / SVG，再手动执行 `export-commands` 输出的命令。
7. 打开 PNG 目检。
8. 如果发现拥挤、越界、箭头太多、对齐松散，继续改源文件。
9. 重复导出和质检，直到通过。

### Windows 专用说明

- `render` 和 `export-commands` 会自动判断当前主机是不是 Windows。
- Windows 上 `export-commands` 默认按 PowerShell 输出；如果你更习惯 `cmd.exe`，显式加 `--shell cmd`。
- 如果脚本在 Windows 上没找到可运行 draw.io，会自动进入 source-only 模式，只交付 `.drawio`。
- 如果你的安装目录不在常见位置，优先修改 `config.json` 里的 `runtime.windows_drawio_path_templates`。

### Windows 冒烟测试建议

在真实 Windows 主机上，最小验证顺序建议是：

1. `python3 scripts/drawio_skill.py export-commands --input outputs/demo/topology.drawio --out-dir outputs/demo`
2. 确认输出中的 `Host platform` 是 `windows`，`Command shell` 默认是 `powershell`
3. 执行生成的 PNG 导出命令
4. 运行 `python3 scripts/drawio_skill.py qa-report --input outputs/demo/topology.drawio --out-dir outputs/demo --formats png --strict`
5. 确认 `Should fix: False`

## 7. 风格预设怎么选

### `soft-modern`

适合：

- 甘特图
- 路线图
- 时间线
- 轻量流程图

特征：

- 暖白底
- 柔和粉绿蓝点缀
- 卡片感强
- 少箭头

### `minimal-topology`

适合：

- 网络拓扑图
- 服务关系图
- 系统节点连接图

特征：

- 白底或浅灰白
- 实体节点和虚拟节点区分明确
- 连线短、直、尽量正交
- 默认不加箭头

### `executive-blueprint`

适合：

- 汇报型架构图
- 解决方案蓝图
- 分层系统总览图

特征：

- 蓝灰冷色
- 分区边界清晰
- 标题规整
- 更适合汇报材料风格

## 8. 参考图怎么用

如果用户给你一张参考图，不要直接照抄其业务结构，而是先抽取风格合同。至少关注这 10 项：

- `background_tone`
- `primary_palette`
- `surface_style`
- `node_shape`
- `corner_radius`
- `stroke_weight`
- `shadow_level`
- `connector_style`
- `whitespace_density`
- `text_density`

推荐做法：

1. 在三个预设里选一个最接近的底座。
2. 保留模板的结构骨架。
3. 用参考图覆盖颜色、圆角、节点形态、边框和标题样式。
4. 不把参考图里明显拥挤、错位、箭头过多的缺点一起带过来。

## 9. 参考示范

下面这组命令已经在当前目录实际跑通过，可以直接参考。

### 目标

生成一个 `minimal-topology` 风格的 demo，并导出 `.drawio`、PNG、SVG，再跑 QA。

### 生成 demo 源文件

```bash
python3 /Users/windsky/2026/formula/skills/drawio-modern-diagrams/scripts/drawio_skill.py \
  copy-template \
  --preset minimal-topology \
  --output /Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo/topology-demo.drawio
```

### 导出 PNG / SVG

```bash
/opt/homebrew/bin/drawio -x -f png \
  -o /Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo \
  /Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo/topology-demo.drawio

/opt/homebrew/bin/drawio -x -f svg \
  -o /Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo \
  /Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo/topology-demo.drawio
```

### QA 检查

```bash
python3 /Users/windsky/2026/formula/skills/drawio-modern-diagrams/scripts/drawio_skill.py \
  qa-report \
  --input /Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo/topology-demo.drawio \
  --out-dir /Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo
```

当前实测结果为：

- `Inspect image exists: True`
- `Lint issues: 0`
- `Should fix: False`

对应文件路径：

- `.drawio`：`/Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo/topology-demo.drawio`
- `PNG`：`/Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo/topology-demo.png`
- `SVG`：`/Users/windsky/2026/formula/skills/drawio-modern-diagrams/outputs/demo/topology-demo.svg`

## 10. 常见问题

### Q1：`qa-report` 显示 `Should fix: True`，但 lint 是 0

最常见原因不是图有结构问题，而是 PNG 还没有导出，或者导出的 PNG / SVG 已经落后于最新 `.drawio`。这个命令会同时检查：

- 结构问题数量
- 用于目检的 PNG 是否存在

也就是说，即使 lint 为 0，只要 PNG 不存在或已经过期，它仍会要求继续处理。

### Q2：为什么这个 skill 强调“非必要不要加箭头”

因为很多图的可读性问题都来自箭头过多。对于路线图、蓝图、拓扑图，很多关系可以用：

- 分区
- 卡片归属
- 左右顺序
- 阶段带
- 标题层级

来表达，而不是强行用箭头。

### Q3：什么时候应该保留箭头

只有以下语义不画箭头会产生歧义时，才建议保留：

- 因果关系
- 依赖关系
- 严格方向性
- 请求流向或数据流向

### Q4：lint 通过了，为什么还要人工看 PNG

因为脚本只能发现高概率结构问题，不能可靠判断：

- 观感是否现代
- 留白是否舒服
- 视觉层次是否平衡
- 配色是否和参考图足够接近

### Q5：为什么 `render` 没导出 PNG，只给了 `.drawio`

这是 source-only 模式，通常表示下面两种情况之一：

- 当前机器没有可运行的 draw.io CLI
- 当前机器虽然装了 draw.io，但当前环境里的 direct CLI 和 helper 都不可用

这不是业务图本身失败，而是运行环境不支持自动导出。此时：

- `.drawio` 仍然有效
- lint 仍然可以继续跑
- 如果你确实需要图片，请在可运行 draw.io 的终端环境里手动执行 `export-commands` 提供的命令
- 现在 `source-only` 下不会再把“没法做 PNG 目检”误判成通过；如果缺少 PNG / SVG，`should_fix` 会继续是 `true`

### Q6：为什么 `.drawio` 打不开，提示文件格式错误

一个常见原因是文件前后被误加了额外内容，例如：

- YAML front matter
- Markdown 标题或说明文字
- 代码围栏
- LLM 回复中的解释段落

现在这个 skill 已经会在 `render`、`qa-report`、`export-commands` 和 `lint_drawio.py` 中自动检测并修复这类问题；如果你想单独修复，也可以直接运行 `sanitize-input`。

## 11. 当前 skill 的已知局限

从当前实现看，这个 skill 已经能覆盖“模板复制 + 运行时探测 + 执行导出 / source-only 回退 + 生成导出命令 + 结构检查 + 新鲜度校验 + 人工复核”的主流程，但还存在这些局限：

- `render` 现在已经能在 macOS 上尝试 direct CLI 和 `launchctl` helper，并在 Windows / 受限环境下安全回退到 source-only 模式；但它还没有覆盖更多平台上的外部执行器。
- `export-commands` 现在已支持 POSIX / PowerShell / CMD 三种命令风格，但本轮没有在真实 Windows 主机上完成实际执行验证。
- `lint_drawio.py` 已增加小字号和元素重叠检查，但仍未覆盖对齐抖动、间距不一致等更细的版式规则。
- 对“参考图片风格提炼”只有规则，没有辅助命令或结构化输出。
- 默认逻辑主要围绕单页图；多页 `.drawio` 的处理还不够明确。

## 12. 如果你准备继续增强这个 skill，建议优先做什么

建议优先级如下：

1. 继续扩展 helper / 外部调度方案，覆盖不止 macOS `launchctl` 一种执行器。
2. 让 `render` 在更多受限环境里自动判断“direct / helper / source-only”三种模式。
3. 给 `lint_drawio.py` 增加更多版式规则，例如对齐、间距和层次密度检查。
4. 增加参考图风格合同的结构化输出能力。
5. 明确支持多页 `.drawio` 的检查策略。

如果你后面要继续迭代这个 skill，最值得先补的是第 1 和第 3 项。
