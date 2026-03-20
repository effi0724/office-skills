# Style Profiles

## Quick Selection

- `soft-modern`: 适合甘特图、路线图、轻量流程图。特点是暖白背景、柔和粉绿蓝点缀、卡片感强。
- `minimal-topology`: 适合网络拓扑图、节点关系图、系统连接图。特点是白底、低对比边框、实体节点与虚拟网关区分清楚。
- `executive-blueprint`: 适合汇报型架构图、方案蓝图、分层系统图。特点是冷静蓝灰色、结构感更强、标题和分区更规整。

## Profile Details

### `soft-modern`

- 推荐图类型：`gantt` `roadmap` `timeline` `process`
- 推荐模板：`assets/modern-gantt-template.drawio`
- 关键词：现代、清新、柔和、卡片式、留白充足
- 视觉约束：
  - 背景偏暖白
  - 圆角中等偏大
  - 使用淡粉、淡绿、淡蓝做阶段区分
  - 连线极少，优先用列、阶段带和卡片表示顺序

### `minimal-topology`

- 推荐图类型：`topology` `network` `service-map`
- 推荐模板：`assets/minimal-topology-template.drawio`
- 关键词：极简、网络图、技术感、克制、节点区分明确
- 视觉约束：
  - 画布白或浅灰白
  - 实体计算节点用实线卡片或服务器样式
  - 虚拟功能网关用虚线、六边形或轻量中枢样式
  - 连线短、直、尽量正交，避免跨越节点
  - 默认不加箭头，除非方向性必须表达

### `executive-blueprint`

- 推荐图类型：`architecture` `system` `solution` `topology`
- 推荐模板：`assets/executive-blueprint-template.drawio`
- 关键词：蓝图、规整、汇报感、专业、冷静
- 视觉约束：
  - 冷白或浅蓝白背景
  - 分区边界更清晰
  - 标题和域标签更规整
  - 适合大纲式结构图和汇报材料中的总览页

## Matching a User Reference Image

当用户提供参考图片时，先提炼成一份“风格合同”，再用于绘图。至少提取以下内容：

- `background_tone`: 暖白、纯白、浅蓝灰、深色等
- `primary_palette`: 主色和强调色
- `surface_style`: 卡片、分区、标签的填充方式
- `node_shape`: 矩形、圆角卡片、胶囊、六边形、服务器样式
- `corner_radius`: 圆角大小
- `stroke_weight`: 边框粗细和是否虚线
- `shadow_level`: 无阴影、轻阴影、明显悬浮感
- `connector_style`: 直线、正交线、曲线、有无箭头
- `whitespace_density`: 留白宽松、中等、紧凑
- `text_density`: 标签少而短，还是信息密集

## Matching Strategy

1. 先在三个预设中选最近的一种作为基础。
2. 只把参考图的视觉语言迁移过来，不复制它的业务结构。
3. 优先复用模板中的排版骨架，再覆盖颜色、节点形状、边框和标题样式。
4. 如果参考图很花，但当前任务是网络拓扑图，仍要保持连接关系清楚，不能为了“像”而牺牲可读性。

## What to Avoid

- 不要机械复制参考图中的所有装饰元素。
- 不要因为追求相似而引入过多箭头或复杂背景。
- 不要把参考图的错位、拥挤、过小字号带进新图。
