# GitHub Weekly Report 使用说明

## 1. 能力概览
- 支持单仓和多仓汇总。
- 支持三种范围：
  - `current_week`
  - `date_range`
  - `commit_compare`
- 支持全局过滤，也支持每个仓库单独覆盖过滤。
- 输出固定为：
  - `weekly-summary.md`
  - `weekly-report.md`
  - `source-data.json`

## 2. GitHub 认证与密钥配置
这个 skill 不会在 JSON 配置里保存任何 GitHub 密钥。认证有两种推荐方式。

### 方式 A：本机 `gh auth login`
适合本地长期使用。

```bash
gh auth login -h github.com -s repo,read:org
```

说明：
- 如果要读取私有仓库，至少要有 `repo`。
- 如果目标仓库属于组织，或需要读取组织成员可见仓库，建议再加 `read:org`。
- 登录后的凭据由 `gh` 自己保存在系统钥匙串或本地凭据存储中。

### 方式 B：环境变量 `GH_TOKEN` / `GITHUB_TOKEN`
适合 CI、服务器、临时会话。

```bash
export GH_TOKEN=ghp_xxx
```

或

```bash
export GITHUB_TOKEN=ghp_xxx
```

建议权限：
- Classic PAT：
  - 私有仓库至少 `repo`
  - 组织仓库建议再加 `read:org`
- Fine-grained PAT：
  - Repository metadata: Read-only
  - Contents: Read-only
  - Pull requests: Read-only

注意：
- 不要把 token 写进 `config*.json`。
- 不要把 token 提交到 Git 仓库。
- 不要把 token 写进 `source-data.json`、周报文件或截图。

## 3. 配置 GitHub 仓库

### 推荐格式：`repos[]`
首选 `repos` 数组。每个元素代表一个仓库。

字段：
- `owner`：GitHub owner 或组织名
- `name`：仓库名
- `default_branch`：默认分支，通常是 `main`
- `alias`：可选，周报里的显示名称
- `filters`：可选，仅对该仓库生效的覆盖过滤

仓库级 `filters` 支持：
- `authors`
- `include_paths`
- `exclude_paths`
- `exclude_merge_commits`

如果仓库级 `filters` 省略某个字段，就继承全局 `filters`。

### 兼容格式：`repo`
旧版单仓配置仍可使用：

```json
{
  "repo": {
    "owner": "effi0724",
    "name": "office-skills",
    "default_branch": "main"
  }
}
```

但后续建议统一迁移到 `repos[]`。

## 4. 配置示例

### 单仓示例
参考 [config.office-skills.example.json](/Users/windsky/2026/formula/skills/github-weekly-report/config.office-skills.example.json)

### 多仓示例
参考 [config.multi-repos.example.json](/Users/windsky/2026/formula/skills/github-weekly-report/config.multi-repos.example.json)

多仓典型配置：

```json
{
  "repos": [
    {
      "owner": "effi0724",
      "name": "office-skills",
      "default_branch": "main",
      "alias": "office-skills"
    },
    {
      "owner": "effi0724",
      "name": "rtsp2mqtt",
      "default_branch": "main",
      "alias": "rtsp2mqtt",
      "filters": {
        "include_paths": ["docs/**", "tests/**"]
      }
    }
  ],
  "range": {
    "mode": "current_week",
    "start": "",
    "end": "",
    "base_sha": "",
    "head_sha": ""
  },
  "filters": {
    "authors": ["effi0724"],
    "include_paths": [],
    "exclude_paths": [],
    "exclude_merge_commits": true
  },
  "report": {
    "language": "zh-CN",
    "style": "manager",
    "output_dir": "outputs"
  }
}
```

## 5. 常用运行方式

### 先验证配置和权限
```bash
python3 scripts/github_weekly_report.py validate-config --config config.multi-repos.example.json
```

### 先预览命中的仓库和提交
```bash
python3 scripts/github_weekly_report.py preview-range --config config.multi-repos.example.json
```

### 直接生成周报
```bash
python3 scripts/github_weekly_report.py generate-report --config config.multi-repos.example.json
```

## 6. 范围配置说明

### 本周
```json
"range": {
  "mode": "current_week",
  "start": "",
  "end": "",
  "base_sha": "",
  "head_sha": ""
}
```

### 日期范围
```json
"range": {
  "mode": "date_range",
  "start": "2026-03-20",
  "end": "2026-03-24",
  "base_sha": "",
  "head_sha": ""
}
```

### Commit compare
```json
"range": {
  "mode": "commit_compare",
  "start": "",
  "end": "",
  "base_sha": "abc1234",
  "head_sha": "def5678"
}
```

## 7. 输出说明
输出目录默认在 skill 目录下的 `outputs/<label>/`。

例如：
- [weekly-summary.md](/Users/windsky/2026/formula/skills/github-weekly-report/outputs/2026-W13/weekly-summary.md)
- [weekly-report.md](/Users/windsky/2026/formula/skills/github-weekly-report/outputs/2026-W13/weekly-report.md)
- [source-data.json](/Users/windsky/2026/formula/skills/github-weekly-report/outputs/2026-W13/source-data.json)

多仓场景下，输出会额外包含：
- 仓库覆盖
- 每个完成事项所属仓库
- 证据附录中的仓库标签

## 8. 常见问题

### `gh auth status` 通过了，但脚本还是报 GitHub 访问失败
- 通常是当前环境没有网络权限，或者 `gh api` 无法访问 `api.github.com`。
- 在受限环境里，需要给执行命令放开网络。

### 明明配置了多个仓库，但只统计到一个
- 先跑 `preview-range` 看每个仓库的命中数。
- 确认范围是否覆盖到这些仓库的实际提交日期。
- 检查仓库级 `filters.include_paths` 是否把提交都过滤掉了。

### 多仓配置里作者不同怎么办
- 直接在对应仓库对象里写自己的 `filters.authors`。
- 如果省略仓库级作者过滤，就继承全局 `filters.authors`。

### 能不能把 token 放进 JSON 配置
- 不要这样做。这个 skill 明确要求密钥只通过 `gh` 登录态或环境变量传入。
