# PythonScripts

A lightweight collection of small, single-file Python utilities and experiments. Each script is self-contained and focuses on doing one thing well.

## Getting started

- Requirements: Python 3.9+ (3.11 recommended)
- Optional: Create a virtual environment if a script has dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
```

## Running scripts

- Most scripts can be run directly with Python:
  - `python3 path/to/script.py` or `python3 script_name`
- If a script has a shebang (`#!/usr/bin/env python3`) and executable bit, you can run it directly:
  - `./script_name`
- Many scripts support `-h/--help` for usage:
  - `python3 script_name -h`

## Dependencies

- If a script uses third‑party packages, it will mention them in its header/docstring.
- Install per-script requirements as needed, for example:
  - `pip install requests rich` (example)

## Conventions

- Single-file scripts live at the repo root (or a subfolder if they grow).
- Prefer:
  - A short module docstring explaining purpose, inputs/outputs, and examples
  - `argparse` for CLI flags and `-h/--help`
  - Clear exit codes and explicit error messages
  - No secrets in code—use environment variables where necessary

## Adding a new script

1. Create a new file with a descriptive name (e.g., `foo_bar_tool.py` or `foo_bar_tool`).
2. Include a docstring with:
   - What it does
   - How to run it
   - Inputs/outputs (files, env vars)
3. Use `argparse` if it has parameters.
4. Document any dependencies in the docstring and keep them minimal.
5. Test locally and add example commands to the docstring.

## Project layout (informal)

- Root contains individual scripts and this README.
- Temporary outputs or data files should be git‑ignored locally if large or generated.

## Tips

- Use `python -m pip install -r requirements.txt` if a script provides one.
- Use `ruff` or `black` if you prefer auto-formatting (optional).
- On macOS: `python3` refers to the system or Homebrew Python; prefer virtualenvs per script that needs packages.

## License

No license specified yet. Add one if sharing publicly (e.g., MIT/Apache-2.0).
