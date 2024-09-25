import subprocess
import time
import tomllib


def main():
    global_start = time.perf_counter()
    _print_cyan("Detoxing begins:")
    is_successful = _setup() & _detox() & _teardown()
    global_stop = time.perf_counter()
    if is_successful:
        _print_cyan(f"Detoxing took: {global_stop - global_start}")
    else:
        _print_purple(f"Unsuccessful detoxing took: {global_stop - global_start}")


def _detox():
    data = _parse()
    for key, val in data.items():
        print("#########################################")
        _print_yellow(f"{key.upper()}:")
        start = time.perf_counter()

        install = ""
        run = ""
        deps = val.get("dependencies", [])
        if isinstance(deps, list):
            install = " ".join(deps)
        else:
            install += f"{deps}"

        cmds = val.get("commands", [])
        if isinstance(cmds, list):
            run = " && ".join(cmds)
        else:
            run += f"{cmds}"

        install = "pip install " + install

        is_successful = _run_subprocess(f"source .detoxenv/bin/activate && {install} && {run}")
        if not is_successful:
            _print_red(f"{key.upper()} failed")
            return False

        stop = time.perf_counter()
        _print_green(f"{key.upper()} succeeded! Took:  {stop - start}")
    print("#########################################")
    return True


def _parse():
    with open("detox.toml", "rb") as f:
        data = tomllib.load(f)
    return data


def _run_subprocess(run):
    is_successful = True
    with subprocess.Popen(
        run, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, executable="/bin/bash"
    ) as proc:
        # Use read1() instead of read() or Popen.communicate() as both blocks until EOF
        # https://docs.python.org/3/library/io.html#io.BufferedIOBase.read1
        while (text := proc.stdout.read1().decode("utf-8")) or (
            err := proc.stderr.read1().decode("utf-8")
        ):
            if text:
                print(text, end="", flush=True)
                if "error" in text.lower():
                    is_successful = False
            elif err:
                _print_red(err, end="", flush=True)
                is_successful = False
    return is_successful


def _setup():
    print("Creating venv...")
    prepare = "python3 -m venv .detoxenv"
    is_successful = _run_subprocess(prepare)
    if not is_successful:
        _print_red("Something went wrong :(")
        return False
    return True


def _teardown():
    teardown = "rm -rf .detoxenv"
    print("Removing venv...")
    is_successful = _run_subprocess(teardown)
    if not is_successful:
        _print_red("Something went wrong :(")
        return False
    return True


def _print_red(msg, end="\n", flush=False):
    print(f"\033[91m{msg}\033[00m", end=end, flush=flush)


def _print_green(msg, end="\n", flush=False):
    print(f"\033[92m{msg}\033[00m", end=end, flush=flush)


def _print_yellow(msg, end="\n", flush=False):
    print(f"\033[93m{msg}\033[00m", end=end, flush=flush)


def _print_purple(msg, end="\n", flush=False):
    print(f"\033[94m{msg}\033[00m", end=end, flush=flush)


def _print_cyan(msg, end="\n", flush=False):
    print(f"\033[96m{msg}\033[00m", end=end, flush=flush)


if __name__ == "__main__":
    main()
