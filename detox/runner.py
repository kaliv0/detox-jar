import os
import subprocess
import sys
import time
import tomllib
from itertools import chain

from detox.logger import DetoxicoLogger


class DetoxRunner:
    CONFIG_FILE = "./detox.toml"
    TMP_VENV = ".detoxenv"

    def __init__(self):
        self.data = None
        self.all_jobs = None
        self.cli_jobs = None

        self.successful_jobs = []
        self.failed_jobs = []

        self.is_toml_file_valid = False
        self.is_setup_successful = False
        self.is_teardown_successful = False
        self.is_detox_successful = True  # needed for bitwise &

    @property
    def skipped_jobs(self):
        return [
            job for job in self.all_jobs if job not in chain(self.failed_jobs, self.successful_jobs)
        ]

    @property
    def job_suite(self):
        if self.cli_jobs:
            self.all_jobs = self.cli_jobs
        elif "run" in self.data:
            jobs = dict(self.data["run"].items())
            if "suite" not in jobs:
                DetoxicoLogger.error("Encountered error: missing key 'suite' in 'run' table")
                return None
            self.all_jobs = jobs["suite"]
        else:
            self.all_jobs = list(self.data.keys())
        return ((k, self.data[k]) for k in self.all_jobs)

    # main flow
    def run(self, args):
        global_start = time.perf_counter()
        DetoxicoLogger.info("Detoxing begins:")
        self._run_detox_stages(args)
        global_stop = time.perf_counter()

        if self.is_detox_successful:
            DetoxicoLogger.info(f"All jobs succeeded! {self.successful_jobs}")
            DetoxicoLogger.info(f"Detoxing took: {global_stop - global_start}")
        else:
            DetoxicoLogger.fail(f"Unsuccessful detoxing took: {global_stop - global_start}")
            DetoxicoLogger.error(f"Failed jobs: {self.failed_jobs}")
            DetoxicoLogger.info(
                f"Successful jobs: {[x for x in self.successful_jobs if x not in self.failed_jobs]}"
            )
            if self.skipped_jobs:
                DetoxicoLogger.fail(f"Skipped jobs: {self.skipped_jobs}")

    def _run_detox_stages(self, args):
        self._read_file()
        if not self.is_toml_file_valid:
            DetoxicoLogger.fail("Detoxing failed: missing or empty detox.toml file")
            sys.exit(1)

        is_valid, error_job = self._read_args(args)
        if not is_valid:
            DetoxicoLogger.fail(f"Detoxing failed: '{error_job}' not found in detox.toml jobs")
            sys.exit(1)

        self._setup()
        if not self.is_setup_successful:
            DetoxicoLogger.fail("Detoxing failed :(")
            sys.exit(1)

        self._run_jobs()
        for _ in range(3):
            self._teardown()
            if self.is_teardown_successful:
                break

    def _read_file(self):
        if not os.path.exists(self.CONFIG_FILE) or os.path.getsize(self.CONFIG_FILE) == 0:
            self.is_toml_file_valid = False
            return

        with open(self.CONFIG_FILE, "rb") as f:
            self.data = tomllib.load(f)
        self.is_toml_file_valid = bool(self.data)

    def _read_args(self, args):
        if args.jobs is None:
            return True, None
        for job in args.jobs:
            if job not in self.data:
                return False, job
        self.cli_jobs = args.jobs
        return True, None

    # setup environment
    def _setup(self):
        DetoxicoLogger.log("Creating venv...")
        prepare = f"python3 -m venv {self.TMP_VENV}"
        is_successful = self._run_subprocess(prepare)
        if is_successful:
            self.is_setup_successful = True
        else:
            DetoxicoLogger.error("Failed creating new virtual environment")
            self.is_setup_successful = False

    def _teardown(self):
        teardown = f"rm -rf {self.TMP_VENV}"
        DetoxicoLogger.log("Removing venv...")
        is_successful = self._run_subprocess(teardown)
        if is_successful:
            self.is_teardown_successful = True
        else:
            DetoxicoLogger.error("Failed removing virtual environment")
            self.is_teardown_successful = False

    def _run_jobs(self):
        if not self.job_suite:
            self.is_detox_successful = False
            return

        for table, table_entries in self.job_suite:
            DetoxicoLogger.log("#########################################")
            DetoxicoLogger.start(f"{table.upper()}:")
            start = time.perf_counter()

            install = self._build_install_command(table_entries)
            run = self._build_run_command(table, table_entries)
            if not run:
                self.is_detox_successful = False
                return

            cmd = f"source {self.TMP_VENV}/bin/activate"
            if install:
                cmd += f" && {install}"
            cmd += f" && {run}"

            is_successful = self._run_subprocess(cmd)
            if not is_successful:
                self.failed_jobs.append(table)
                DetoxicoLogger.error(f"{table.upper()} failed")
            else:
                stop = time.perf_counter()
                DetoxicoLogger.success(f"{table.upper()} succeeded! Took:  {stop - start}")
                self.successful_jobs.append(table)
            self.is_detox_successful &= is_successful
        DetoxicoLogger.log("#########################################")

    # build shell commands
    @staticmethod
    def _build_install_command(table_entries):
        deps = table_entries.get("dependencies", None)
        if not deps:
            return

        install = ""
        if isinstance(deps, list):
            install = " ".join(deps)
        else:
            install += f"{deps}"
        install = "pip install " + install
        return install

    def _build_run_command(self, table, table_entries):
        run = ""
        cmds = table_entries.get("commands", None)
        if not cmds:
            self.failed_jobs.append(table)
            DetoxicoLogger.error(
                f"Encountered error: 'commands' in '{table}' table cannot be empty or missing"
            )
            return

        if isinstance(cmds, list):
            run = " && ".join(cmds)
        else:
            run += f"{cmds}"
        return run

    # execute shell commands
    @staticmethod
    def _run_subprocess(run):
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
                    is_successful = False
                    DetoxicoLogger.error(err, end="", flush=True)
        return is_successful
