# tests/unit/test_mission_cli.py
from unittest.mock import patch

from src.interface.cli.main import build_parser, cmd_mission


def test_parser_accepts_mission_subcommands():
    parser = build_parser()
    args = parser.parse_args(["mission", "resume", "job-7"])
    assert args.command == "mission" and args.mission_command == "resume" and args.job_id == "job-7"

    args = parser.parse_args(["mission", "scan", "--companies", "Acme", "BigCo",
                              "--no-aggregators", "--filter-h1b"])
    assert args.companies == ["Acme", "BigCo"]
    assert args.include_aggregators is False and args.filter_h1b is True

    args = parser.parse_args(["mission", "status"])
    assert args.mission_command == "status"


def test_scan_subcommand_calls_run_once():
    with patch("src.interface.cli.main._make_discovery_agent") as factory:
        factory.return_value.run_once.return_value = {"jobs_ingested": 7,
                                                      "sources": ["a"],
                                                      "duration_sec": 1.0}
        parser = build_parser()
        args = parser.parse_args(["mission", "scan"])
        assert cmd_mission(args) == 0
        factory.return_value.run_once.assert_called_once()
        kwargs = factory.return_value.run_once.call_args.kwargs
        assert kwargs["company_names"] is None


def test_unknown_mission_command_returns_2():
    import argparse
    ns = argparse.Namespace(command="mission", mission_command="bogus")
    assert cmd_mission(ns) == 2
