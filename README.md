<p align="center">
  <img src="https://github.com/kaliv0/detox-jar/blob/main/assets/detox-jar.jpg?raw=true" width="250" alt="Detox jar">
</p>

# Detox jar

![Python 3.x](https://img.shields.io/badge/python-3.11-blue?style=flat-square&logo=Python&logoColor=white)
[![PyPI](https://img.shields.io/pypi/v/detox-jar.svg)](https://pypi.org/project/detox-jar/)
[![Downloads](https://static.pepy.tech/badge/detox-jar)](https://pepy.tech/projects/detox-jar)

<br>Command line automation tool in pure Python

---------------------------
### How to use
- Describe jobs as tables in a config file called 'detox' (choose between .toml, .json or .yaml format).
<br>(Put the config inside the root directory of your project)
```toml
[test]
description = "test project"
dependencies = ["pytest", "pytest-cov"]
commands = "pytest -vv --disable-warnings -s --cache-clear"
```

- <i>description</i> and <i>dependencies</i> could be optional but not <i>commands</i>
```toml
[no-deps]
commands = "echo 'Hello world'"
```

- <i>dependencies</i> and <i>commands</i> could be strings or (in case of more than one) a list of strings
```toml
commands = ["ruff check --fix", "ruff format --line-length=100 ."]
```

- You could provide a [run] table inside the toml file with a <i>'suite'</i> - list of selected jobs to run
```toml
[run]
suite = ["lint", "format", "test"]
```
---------------------------
- Run the tool in the terminal with a simple <b>'detox'</b> command
```shell
$ detox
```
```shell
(logs omitted...)
$ All jobs succeeded! ['lint', 'format', 'test']
Detoxing took: 14.088007061000098
```
- In case of failing jobs you get general stats
```shell
(logs omitted...)
$ Unsuccessful detoxing took: 13.532951637999759
Failed jobs: ['format']
Successful jobs: ['lint', 'test']
```
or
```shell
$ Unsuccessful detoxing took: 8.48367640699962
Failed jobs: ['format']
Successful jobs: ['lint']
Skipped jobs: ['test']
```
---------------------------
- You could run specific jobs in the command line
```shell
$ detox -j lint
```
or a list of jobs
```shell
$ detox -j lint format
```
<b>NB:</b> If there is a [run] table in the toml file the jobs specified in the command line take precedence
