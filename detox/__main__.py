import argparse

from detox.runner import DetoxRunner
from detox import __version__


def get_command_line_args():
    parser = argparse.ArgumentParser(
        prog="detox",
        description="Automation tool",
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s v{__version__}")
    parser.add_argument(
        "-j",
        "--job",
        help="pick a job from detox.toml file to run",
    )
    return parser.parse_args()


# TODO: remove
if __name__ == "__main__":
    args = get_command_line_args()
    DetoxRunner().run(args)
