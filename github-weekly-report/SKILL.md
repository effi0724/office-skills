---
name: github-weekly-report
description: 基于 GitHub 一个或多个仓库、时间范围或 commit 范围自动生成中文工作总结和周报，支持按作者与路径过滤，并补充关联 PR 标题、描述与文件范围。当用户要求“按 GitHub 仓库生成本周工作总结 / 周报 / 周报草稿 / 项目周进展 / 提交周报”时使用。
---

# GitHub Weekly Report Skill

详细中文使用说明见 `USAGE.zh-CN.md`。

## Goal
给定 GitHub 一个或多个仓库与范围配置，完成以下闭环：
1) 读取配置并校验 `gh` 登录状态，
2) 解析本周、日期范围或 commit compare 范围，
3) 拉取各仓库命中的 commits，并补充 changed files 与关联 PR，
4) 生成中文 `weekly-summary.md`、`weekly-report.md` 与 `source-data.json`，
5) 向用户返回输出路径、范围说明与风险提示。

## How to run
- 配置：优先参考本技能目录下的 `config.example.json`、`config.office-skills.example.json` 与 `config.multi-repos.example.json`。
- 首次使用前先校验环境：
  - `python3 scripts/github_weekly_report.py validate-config --config config.office-skills.example.json`
- 若要先确认范围与命中提交：
  - `python3 scripts/github_weekly_report.py preview-range --config config.office-skills.example.json`
- 若要直接生成周报：
  - `python3 scripts/github_weekly_report.py generate-report --config config.office-skills.example.json`
- 运行顺序固定为：
  - 校验配置与 GitHub 访问
  - 解析范围
  - 遍历仓库列表并拉取 commits
  - 拉取 commit 详情与关联 PR
  - 生成多仓汇总、工作项、涉及范围、风险与建议
  - 写入输出目录

## Config contract
- 优先使用 `repos[]`，每个元素支持：
  - `owner`、`name`、`default_branch`
  - 可选 `alias`，用于周报展示名
  - 可选 `filters`，覆盖该仓库的作者和路径过滤
- 兼容旧版 `repo.owner`、`repo.name`、`repo.default_branch` 单仓配置。
- `range.mode`：支持 `current_week`、`date_range`、`commit_compare`。
- `range.start`、`range.end`：仅 `date_range` 使用；支持 `YYYY-MM-DD` 或完整 ISO 时间。
- `range.base_sha`、`range.head_sha`：仅 `commit_compare` 使用。
- `filters.authors`：全局作者白名单；为空时默认使用当前 `gh` 登录用户。
- `filters.include_paths`、`filters.exclude_paths`：使用 glob 风格路径过滤。
- `filters.exclude_merge_commits`：是否跳过 merge commit。
- `report.language`：首版固定 `zh-CN`。
- `report.style`：首版固定 `manager`。
- `report.output_dir`：输出目录，默认建议为 `outputs`。

## Output contract
- 目录按范围标签落盘，例如 `outputs/2026-W13/`。
- 固定输出 3 个文件：
  - `weekly-summary.md`
  - `weekly-report.md`
  - `source-data.json`
- `weekly-summary.md` 面向汇报场景，保持一页内可读，并显示仓库覆盖情况。
- `weekly-report.md` 包含仓库覆盖、完成事项、业务影响、涉及范围、风险/阻塞、下周建议与证据附录。
- `source-data.json` 保存归一化原始数据，便于复查和二次加工。

## Working style
- 默认生成中文管理层可读版本，先讲结果，再补证据。
- 优先使用 PR 标题概括工作项；没有 PR 时退回 commit 标题。
- 多仓场景下保留仓库维度，不把不同仓库的证据混成匿名列表。
- 风险与建议要明确标出“由脚本自动推断”的地方，避免伪精确。
- 当没有 Linear key 或没有关联 PR 时，允许降级，但必须明确提示。

## What to present to the user
1) 给出实际输出目录路径。
2) 说明本次仓库列表、范围，以及是否使用了每仓库覆盖过滤。
3) 说明命中了多少个仓库、多少个 commits、多少个 PR、主要覆盖了哪些范围。
4) 若存在数据缺口，明确指出，例如：
   - 没有关联 PR
   - 没有 Linear key
   - 某些已配置仓库没有命中提交
   - 过滤条件过严导致无提交
   - commit 文案过短，周报只能做弱总结

## Constraints (MUST)
- 不要在配置中保存 GitHub Token；认证应通过 `gh auth login` 或环境变量 `GH_TOKEN` / `GITHUB_TOKEN` 提供。
- 不要跳过 `validate-config` 与范围解析；失败要尽早暴露。
- 输出目录必须包含原始 `source-data.json`，不能只交 Markdown。
- 本技能首版不把生成周报自动写回 Linear；Linear 只跟踪开发流程。
- 关联 PR、Linear key、风险与下周建议若无法可靠推断，必须显式写成“待人工补充”而不是伪造细节。
