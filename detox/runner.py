import os
import subprocess
import sys
import time
import tomllib
from itertools import chain

from detox.logger import ToxicoLogger


class DetoxRunner:
    CONFIG_FILES = ["detox.toml", "detox.json", "detox.yaml", "detox.xml"]
    TMP_VENV = ".detoxenv"

    def __init__(self):
        self.data = None
        self.all_jobs = []
        self.cli_jobs = []
        self.successful_jobs = []
        self.failed_jobs = []

        self.is_config_file_valid = False
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
                ToxicoLogger.error("Encountered error: missing key 'suite' in 'run' table")
                return None
            self.all_jobs = jobs["suite"]
        else:
            self.all_jobs = list(self.data.keys())
        return ((k, self.data[k]) for k in self.all_jobs)

    # main flow
    def run(self, args):
        global_start = time.perf_counter()
        ToxicoLogger.info("Detoxing begins:")
        self._run_detox_stages(args)
        global_stop = time.perf_counter()

        if self.is_detox_successful:
            ToxicoLogger.info(f"All jobs succeeded! {self.successful_jobs}")
            ToxicoLogger.info(f"Detoxing took: {global_stop - global_start}")
        else:
            ToxicoLogger.fail(f"Unsuccessful detoxing took: {global_stop - global_start}")
            if self.failed_jobs:  # in case parsing fails before any job is run
                ToxicoLogger.error(f"Failed jobs: {self.failed_jobs}")
            if self.successful_jobs:
                ToxicoLogger.info(
                    f"Successful jobs: {[x for x in self.successful_jobs if x not in self.failed_jobs]}"
                )
            if self.skipped_jobs:
                ToxicoLogger.fail(f"Skipped jobs: {self.skipped_jobs}")

    def _run_detox_stages(self, args):
        self._handle_config_file()
        if not self.is_config_file_valid:
            ToxicoLogger.fail("Detoxing failed: missing or invalid config file")
            sys.exit(1)

        is_valid, error_job = self._read_args(args)
        if not is_valid:
            ToxicoLogger.fail(f"Detoxing failed: '{error_job}' not found in jobs")
            sys.exit(1)

        self._setup()
        if not self.is_setup_successful:
            ToxicoLogger.fail("Detoxing failed :(")
            sys.exit(1)

        self._run_jobs()
        for _ in range(3):
            self._teardown()
            if self.is_teardown_successful:
                break

    def _handle_config_file(self):
        for config in self.CONFIG_FILES:
            config_path = os.path.join(os.getcwd(), config)
            if not os.path.exists(config_path):
                continue
            if not os.path.getsize(config_path):
                self.is_config_file_valid = False
                return
            return self._read_config_file(config_path)
        # if we happen to be here (after the loop) no file is read and we just return

    def _read_config_file(self, config_path):
        with open(config_path, "rb") as f:
            _, extension = os.path.splitext(config_path)
            match extension:
                case ".toml":
                    import tomllib

                    self.data = tomllib.load(f)
                case ".json":
                    import json

                    self.data = json.load(f)
                case ".yaml":
                    import yaml

                    self.data = yaml.safe_load(f)
                case _:
                    self.is_config_file_valid = False
                    return
        self.is_config_file_valid = bool(self.data)

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
        ToxicoLogger.log("Creating venv...")
        prepare = f"python3 -m venv {self.TMP_VENV}"
        is_successful = self._run_subprocess(prepare)
        if is_successful:
            self.is_setup_successful = True
        else:
            ToxicoLogger.error("Failed creating new virtual environment")
            self.is_setup_successful = False

    def _teardown(self):
        teardown = f"rm -rf {self.TMP_VENV}"
        ToxicoLogger.log("Removing venv...")
        is_successful = self._run_subprocess(teardown)
        if is_successful:
            self.is_teardown_successful = True
        else:
            ToxicoLogger.error("Failed removing virtual environment")
            self.is_teardown_successful = False

    def _run_jobs(self):
        if not self.job_suite:
            self.is_detox_successful = False
            return

        for table, table_entries in self.job_suite:
            ToxicoLogger.log("#########################################")
            ToxicoLogger.start(f"{table.upper()}:")
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
                ToxicoLogger.error(f"{table.upper()} failed")
            else:
                stop = time.perf_counter()
                ToxicoLogger.success(f"{table.upper()} succeeded! Took:  {stop - start}")
                self.successful_jobs.append(table)
            self.is_detox_successful &= is_successful
        ToxicoLogger.log("#########################################")

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
            ToxicoLogger.error(
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
                    ToxicoLogger.log(text, end="", flush=True)
                    if "error" in text.lower():
                        is_successful = False
                elif err:
                    is_successful = False
                    ToxicoLogger.error(err, end="", flush=True)
        return is_successful
