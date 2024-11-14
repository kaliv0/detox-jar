import os
import subprocess
import sys
import time
from itertools import chain

from detox.logger import ToxicoLogger


class DetoxRunner:
    CONFIG_FILE = "detox"
    CONFIG_FORMATS = [".toml", ".json", ".yaml"]
    TMP_VENV = ".detoxenv"

    def __init__(self):
        self.data = None
        self.all_jobs = []
        self.cli_jobs = []
        self.successful_jobs = []
        self.failed_jobs = []

    @property
    def skipped_jobs(self):
        return [job for job in self.all_jobs if job not in chain(self.failed_jobs, self.successful_jobs)]

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
        is_detox_successful = self._run_detox_stages(args)
        global_stop = time.perf_counter()

        if is_detox_successful:
            ToxicoLogger.info(f"All jobs succeeded! {self.successful_jobs}")
            ToxicoLogger.info(f"Detoxing took: {global_stop - global_start}")
            # sys.exit()  # TODO
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
            # sys.exit(1) # TODO

    def _run_detox_stages(self, args):
        if not (self._handle_config_file() and self._read_args(args) and self._setup()):
            ToxicoLogger.fail("Detoxing failed")
            sys.exit(1)

        is_detox_successful = self._run_jobs()
        for _ in range(3):
            is_teardown_successful = self._teardown()
            if is_teardown_successful:
                break
        return is_detox_successful

    def _handle_config_file(self):
        for config_fmt in self.CONFIG_FORMATS:
            config_path = os.path.join(os.getcwd(), f"{self.CONFIG_FILE}{config_fmt}")
            if not os.path.exists(config_path):
                continue
            if not os.path.getsize(config_path):
                ToxicoLogger.fail("Empty config file")
                return False
            return self._read_config_file(config_path)
        ToxicoLogger.fail("Config file not found")
        return False

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
                    ToxicoLogger.fail("Invalid config file format")
                    return False
        return bool(self.data)

    def _read_args(self, args):
        if args.jobs is None:
            return True
        for job in args.jobs:
            if job not in self.data:
                ToxicoLogger.fail(f"'{job}' not found in jobs suite")
                return False
        self.cli_jobs = args.jobs
        return True

    # setup environment
    def _setup(self):
        ToxicoLogger.log("Creating venv...")
        prepare = f"python3 -m venv {self.TMP_VENV}"
        if self._run_subprocess(prepare):
            return True
        ToxicoLogger.error("Failed creating new virtual environment")
        return False

    def _teardown(self):
        teardown = f"rm -rf {self.TMP_VENV}"
        ToxicoLogger.log("Removing venv...")
        if self._run_subprocess(teardown):
            return True
        ToxicoLogger.error("Failed removing virtual environment")
        return False

    def _run_jobs(self):
        if not self.job_suite:
            return False

        is_detox_successful = True
        for table, table_entries in self.job_suite:
            ToxicoLogger.log("#########################################")
            ToxicoLogger.start(f"{table.upper()}:")
            start = time.perf_counter()

            install = self._build_install_command(table_entries)
            if not (run := self._build_run_command(table, table_entries)):
                return False

            cmd = f"source {self.TMP_VENV}/bin/activate"
            if install:
                cmd += f" && {install}"
            cmd += f" && {run}"

            if not (is_job_successful := self._run_subprocess(cmd)):
                self.failed_jobs.append(table)
                ToxicoLogger.error(f"{table.upper()} failed")
            else:
                stop = time.perf_counter()
                ToxicoLogger.success(f"{table.upper()} succeeded! Took:  {stop - start}")
                self.successful_jobs.append(table)
            is_detox_successful &= is_job_successful
        ToxicoLogger.log("#########################################")
        return is_detox_successful

    # build shell commands
    @staticmethod
    def _build_install_command(table_entries):
        if not (deps := table_entries.get("dependencies", None)):
            return None
        install = " ".join(deps) if isinstance(deps, list) else deps
        return f"pip install {install}"

    def _build_run_command(self, table, table_entries):
        if not (cmds := table_entries.get("commands", None)):
            self.failed_jobs.append(table)
            ToxicoLogger.error(f"Encountered error: 'commands' in '{table}' table cannot be empty or missing")
            return None
        return " && ".join(cmds) if isinstance(cmds, list) else cmds

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
