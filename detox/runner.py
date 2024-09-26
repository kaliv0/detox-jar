import os
import subprocess
import sys
import time
import tomllib

from detox.logger import DetoxicoLogger


class DetoxRunner:
    CONFIG_FILE = "../detox.toml"
    TMP_VENV = ".detoxenv"

    def __init__(self):
        self.data = None
        self.all_jobs = []
        self.failed_jobs = []

    def suite(self):
        if "run" in self.data:
            jobs = dict(self.data["run"].items())
            if "suite" not in jobs:
                raise KeyError("missing key 'suite' in 'run' table")

            self.all_jobs = jobs["suite"]
            return ((k, self.data[k]) for k in jobs["suite"])
        else:
            self.all_jobs = list(self.data.keys())
            return self.data.items()

    def detox(self):
        is_detox_successful = True

        for key, val in self.suite():
            DetoxicoLogger.log("#########################################")
            DetoxicoLogger.start(f"{key.upper()}:")
            start = time.perf_counter()

            install = self.build_install_command(val)
            run = self.build_run_command(key, val)

            cmd = f"source {self.TMP_VENV}/bin/activate"
            if install:
                cmd += f" && {install}"
            cmd += f" && {run}"

            is_successful = self.run_subprocess(cmd)

            if not is_successful:
                DetoxicoLogger.error(f"{key.upper()} failed")
                self.failed_jobs.append(key)
            else:
                stop = time.perf_counter()
                DetoxicoLogger.success(f"{key.upper()} succeeded! Took:  {stop - start}")
            is_detox_successful &= is_successful
        DetoxicoLogger.log("#########################################")
        return is_detox_successful

    @staticmethod
    def build_install_command(val):  # TODO: rename 'val'
        deps = val.get("dependencies", None)
        if not deps:
            return

        install = ""
        if isinstance(deps, list):
            install = " ".join(deps)
        else:
            install += f"{deps}"
        install = "pip install " + install
        return install

    # @staticmethod
    def build_run_command(self, key, val):  # TODO: rename 'val'
        run = ""
        cmds = val.get("commands", None)
        if not cmds:
            self.failed_jobs.append(key)  # TODO: move outside
            raise KeyError(f"'commands' in '{key}' table cannot be empty or missing")

        if isinstance(cmds, list):
            run = " && ".join(cmds)
        else:
            run += f"{cmds}"
        return run

    def read_file(self):
        if os.path.exists(self.CONFIG_FILE) is False:
            return False
        if os.path.getsize(self.CONFIG_FILE) == 0:
            return False

        with open(self.CONFIG_FILE, "rb") as f:
            self.data = tomllib.load(f)
        # if file contains only comments
        if not self.data:
            return False
        return True

    @staticmethod
    def run_subprocess(run):
        is_successful = True
        with subprocess.Popen(
            run, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, executable="/bin/bash"
        ) as proc:
            # Use read1() instead of read() or Popen.communicate() as both block until EOF
            # https://docs.python.org/3/library/io.html#io.BufferedIOBase.read1
            while (text := proc.stdout.read1().decode("utf-8")) or (
                err := proc.stderr.read1().decode("utf-8")
            ):
                if text:
                    DetoxicoLogger.log(text, end="", flush=True)
                    if "error" in text.lower():
                        is_successful = False
                elif err:
                    DetoxicoLogger.error(err, end="", flush=True)
                    is_successful = False
        return is_successful

    def setup(self):
        DetoxicoLogger.log("Creating venv...")
        prepare = f"python3 -m venv {self.TMP_VENV}"
        is_successful = self.run_subprocess(prepare)
        if not is_successful:
            DetoxicoLogger.error("Something went wrong :(")  # TODO: change message
            self.failed_jobs.append("setup")
            return False
        return True

    def teardown(self):
        teardown = f"rm -rf {self.TMP_VENV}"
        DetoxicoLogger.log("Removing venv...")
        is_successful = self.run_subprocess(teardown)
        if not is_successful:
            DetoxicoLogger.error("Something went wrong :(")  # TODO: change message
            self.failed_jobs.append("teardown")
            return False
        return True


def main():
    global_start = time.perf_counter()
    DetoxicoLogger.info("Detoxing begins:")

    runner = DetoxRunner()
    is_toml_file_valid = runner.read_file()
    if not is_toml_file_valid:
        DetoxicoLogger.fail("Detoxing failed: missing or empty detox.toml file")
        # return
        sys.exit(1)

    # TODO: flags could be class attributes
    is_setup_successful = runner.setup()
    # TODO: if creating venv fails we should exit -> remove also from final check if successful run

    try:
        is_detox_successful = runner.detox()
    except (KeyError, Exception) as e:
        DetoxicoLogger.error(f"Encountered error: {e}")
        is_detox_successful = False

    is_teardown_successful = runner.teardown()

    global_stop = time.perf_counter()
    if is_setup_successful and is_detox_successful and is_teardown_successful:
        DetoxicoLogger.info(f"All jobs succeeded! {runner.all_jobs}")
        DetoxicoLogger.info(f"Detoxing took: {global_stop - global_start}")
    else:
        # TODO: display which jobs were skipped due to raised exception
        DetoxicoLogger.fail(f"Unsuccessful detoxing took: {global_stop - global_start}")
        DetoxicoLogger.fail(f"Failed jobs: {runner.failed_jobs}")
        DetoxicoLogger.fail(
            f"Successful jobs: {[x for x in runner.all_jobs if x not in runner.failed_jobs]}"
        )
