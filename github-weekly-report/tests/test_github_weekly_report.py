from __future__ import annotations

import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "github_weekly_report.py"
SPEC = importlib.util.spec_from_file_location("github_weekly_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class GitHubWeeklyReportTests(unittest.TestCase):
    def test_normalize_config_fills_defaults_for_legacy_single_repo(self) -> None:
        config = MODULE.normalize_config(
            {
                "repo": {"owner": "effi0724", "name": "office-skills"},
                "range": {"mode": "current_week"},
                "filters": {},
                "report": {},
            },
            "effi0724",
        )
        self.assertEqual(len(config["repos"]), 1)
        self.assertEqual(config["repos"][0]["default_branch"], "main")
        self.assertEqual(config["repos"][0]["filters"]["authors"], ["effi0724"])
        self.assertEqual(config["report"]["output_dir"], "outputs")

    def test_normalize_config_supports_multiple_repos(self) -> None:
        config = MODULE.normalize_config(
            {
                "repos": [
                    {"owner": "effi0724", "name": "office-skills", "alias": "office"},
                    {
                        "owner": "effi0724",
                        "name": "rtsp2mqtt",
                        "filters": {"include_paths": ["docs/**"]},
                    },
                ],
                "range": {"mode": "current_week"},
                "filters": {"authors": ["effi0724"], "exclude_merge_commits": True},
                "report": {"language": "zh-CN", "style": "manager", "output_dir": "outputs"},
            },
            "effi0724",
        )
        self.assertEqual(len(config["repos"]), 2)
        self.assertEqual(config["repos"][0]["label"], "office")
        self.assertEqual(config["repos"][1]["filters"]["include_paths"], ["docs/**"])
        self.assertEqual(config["repos"][1]["filters"]["authors"], ["effi0724"])

    def test_resolve_current_week_uses_iso_week(self) -> None:
        now = dt.datetime(2026, 3, 24, 12, 30, tzinfo=dt.timezone.utc)
        range_info = MODULE.resolve_range({"mode": "current_week"}, now=now)
        self.assertEqual(range_info["label"], "2026-W13")
        self.assertEqual(range_info["start_iso"], "2026-03-23T00:00:00Z")

    def test_resolve_commit_compare_label(self) -> None:
        range_info = MODULE.resolve_range(
            {
                "mode": "commit_compare",
                "base_sha": "1234567890abcdef",
                "head_sha": "fedcba0987654321",
            }
        )
        self.assertEqual(range_info["label"], "1234567...fedcba0")

    def test_rendering_uses_fixture_records_for_multi_repo(self) -> None:
        fixture = json.loads((Path(__file__).parent / "fixtures" / "sample_source_data.json").read_text(encoding="utf-8"))
        config = MODULE.normalize_config(
            {
                "repos": fixture["repos"],
                "range": {"mode": "current_week"},
                "filters": {"authors": ["effi0724"], "include_paths": [], "exclude_paths": [], "exclude_merge_commits": True},
                "report": {"language": "zh-CN", "style": "manager", "output_dir": "outputs"},
            },
            "effi0724",
        )
        dataset = MODULE.build_dataset(config, fixture["range_info"], fixture["records"], "effi0724")
        summary = MODULE.render_summary(dataset)
        report = MODULE.render_report(dataset)

        self.assertIn("# 2026-W13 工作总结", summary)
        self.assertIn("仓库覆盖", summary)
        self.assertIn("[office-skills] Add GitHub weekly report skill", summary)
        self.assertIn("rtsp2mqtt", report)
        self.assertIn("JSY-101", report)
        self.assertEqual(dataset["meta"]["configured_repo_count"], 2)

    def test_empty_records_render_gracefully(self) -> None:
        config = MODULE.normalize_config(
            {
                "repos": [{"owner": "effi0724", "name": "office-skills"}],
                "range": {"mode": "current_week"},
                "filters": {"authors": ["effi0724"], "include_paths": [], "exclude_paths": [], "exclude_merge_commits": True},
                "report": {"language": "zh-CN", "style": "manager", "output_dir": "outputs"},
            },
            "effi0724",
        )
        dataset = MODULE.build_dataset(
            config,
            {
                "mode": "current_week",
                "label": "2026-W13",
                "start_iso": "2026-03-23T00:00:00Z",
                "end_iso": "2026-03-24T12:00:00Z",
                "description": "本周（2026-03-23 到 2026-03-24）",
                "base_sha": "",
                "head_sha": "",
            },
            [],
            "effi0724",
        )
        summary = MODULE.render_summary(dataset)
        report = MODULE.render_report(dataset)

        self.assertIn("没有可归纳的工作项", summary)
        self.assertIn("没有命中的提交", report)


if __name__ == "__main__":
    unittest.main()
