# GitHub Weekly Report Output Rules

## Audience
首版默认面向管理层或项目负责人。表达顺序固定为：
1. 本周完成了什么
2. 影响了哪些模块或交付范围
3. 有哪些风险、阻塞或信息缺口
4. 下周建议怎么推进
5. 最后附上精简证据

## Summary format
`weekly-summary.md` 建议控制在一页以内，固定包含：
- 标题
- 仓库与范围概览
- 仓库覆盖
- 本周完成
- 业务影响
- 风险/阻塞
- 下周建议

## Report format
`weekly-report.md` 固定包含：
- 范围概览
- 仓库覆盖
- 完成事项
- 业务影响
- 涉及范围
- 风险/阻塞
- 下周建议
- 证据附录

## Heuristics
- 有关联 PR 时，优先使用 PR 标题作为“完成事项”的标题。
- 没有关联 PR 时，退回到 commit subject。
- 多仓场景下，完成事项和证据必须保留仓库标签。
- `涉及范围` 从 changed files 聚合 top scopes。
- `风险/阻塞` 只写可从 commit/PR 信息中直接推断的内容；其余明确标记为“待人工补充”。
- `下周建议` 允许根据缺少 PR、缺少测试、缺少 Linear key 等信号给出流程性建议。
