"""Common argparse parent parser for --format text|json."""

import argparse


def common_args():
    """Return an argparse ArgumentParser with --format flag for subcommand parents."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: text or json (default: text)",
    )
    return parser


def output(data, fmt):
    """Print data in text or json format."""
    if fmt == "json":
        import json

        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, list):
            for item in data:
                print(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        else:
            print(data)
