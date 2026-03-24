# GitHub Weekly Report

Generate Chinese weekly summaries and weekly reports from one or more GitHub repositories by collecting commits, changed files, and related pull requests within a configured range.

This skill is designed for manager-readable output by default. It keeps the generated report in Chinese (`zh-CN`) and stores normalized source data alongside the Markdown outputs.

## What it does
- Supports a single repository or multiple repositories in one run.
- Supports three range modes:
  - `current_week`
  - `date_range`
  - `commit_compare`
- Filters by author and by path glob patterns.
- Enriches commits with changed files and related pull request metadata when available.
- Writes three outputs for every run:
  - `weekly-summary.md`
  - `weekly-report.md`
  - `source-data.json`

## Authentication
Do not store GitHub tokens in `config*.json`.

Recommended authentication options:

### Option A: `gh auth login`
Best for local development.

```bash
gh auth login -h github.com -s repo,read:org
```

Recommended scopes:
- Private repositories: `repo`
- Organization repositories: `repo,read:org`

### Option B: `GH_TOKEN` or `GITHUB_TOKEN`
Best for CI or short-lived sessions.

```bash
export GH_TOKEN=ghp_xxx
```

or

```bash
export GITHUB_TOKEN=ghp_xxx
```

Recommended permissions:
- Classic PAT:
  - `repo`
  - `read:org` when organization visibility is involved
- Fine-grained PAT:
  - Repository metadata: Read-only
  - Contents: Read-only
  - Pull requests: Read-only

## Quick start
Validate configuration and GitHub access first:

```bash
python3 scripts/github_weekly_report.py validate-config --config config.office-skills.example.json
```

Preview the resolved range and matched commits:

```bash
python3 scripts/github_weekly_report.py preview-range --config config.office-skills.example.json
```

Generate the weekly report:

```bash
python3 scripts/github_weekly_report.py generate-report --config config.office-skills.example.json
```

## Configuration
The preferred format is `repos[]`.

Each repository object supports:
- `owner`
- `name`
- `default_branch`
- optional `alias`
- optional per-repo `filters`

The legacy single-repo format with `repo` is still supported for compatibility, but new usage should move to `repos[]`.

### Global fields
- `range.mode`: `current_week`, `date_range`, or `commit_compare`
- `range.start`
- `range.end`
- `range.base_sha`
- `range.head_sha`
- `filters.authors`
- `filters.include_paths`
- `filters.exclude_paths`
- `filters.exclude_merge_commits`
- `report.language`
- `report.style`
- `report.output_dir`

### Single repository example
```json
{
  "repo": {
    "owner": "effi0724",
    "name": "office-skills",
    "default_branch": "main"
  },
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

### Multiple repository example
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
    "mode": "date_range",
    "start": "2026-03-20",
    "end": "2026-03-24",
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

## Range modes
### `current_week`
Resolves the current week automatically.

### `date_range`
Uses explicit `start` and `end` values. `YYYY-MM-DD` and full ISO timestamps are supported.

### `commit_compare`
Uses `base_sha` and `head_sha` to describe the exact comparison window.

## Outputs
Outputs are written under `report.output_dir/<range-label>/`.

Typical files:
- `outputs/2026-W13/weekly-summary.md`
- `outputs/2026-W13/weekly-report.md`
- `outputs/2026-W13/source-data.json`

The summary is optimized for fast status reporting. The full weekly report includes:
- repository coverage
- completed work items
- business impact
- touched areas
- risks or blockers
- suggested next steps
- evidence appendix

## Example workflow
1. Create a config file from `config.example.json` or `config.multi-repos.example.json`.
2. Authenticate with `gh auth login` or export `GH_TOKEN`.
3. Run `validate-config`.
4. Run `preview-range` and confirm the matched commits look correct.
5. Run `generate-report`.
6. Review the generated Markdown before sharing it externally.

## Notes and limitations
- The generated report language is currently fixed to `zh-CN`.
- The report style is currently fixed to `manager`.
- When a commit has no related pull request, the script falls back to commit titles.
- When no Linear key can be inferred, the report explicitly marks those parts as needing manual follow-up instead of inventing details.

## Related files
- `SKILL.md`: activation and workflow contract for the skill runtime
- `USAGE.zh-CN.md`: detailed Chinese usage guide
- `config.example.json`: generic single-repo example
- `config.multi-repos.example.json`: multi-repo example
- `config.office-skills.example.json`: ready-to-edit example for `office-skills`
