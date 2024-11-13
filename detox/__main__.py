import argparse

from detox.runner import DetoxRunner
from detox import __version__


def get_command_line_args():
    parser = argparse.ArgumentParser(
        prog="detox",
        description="CLI automation tool in pure Python",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s v{__version__}")
    parser.add_argument(
        "-j",
        "--jobs",
        nargs="+",
        help="pick a job from config file to run",
    )
    return parser.parse_args()


def main():
    args = get_command_line_args()
    DetoxRunner().run(args)


if __name__ == "__main__":
    main()
