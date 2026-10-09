"""Run eval tasks in evals/tasks/*.yaml against the configured model and write results.

TODO: for each task -> run agent -> compare against expected behaviour -> PASS/FAIL ->
write evals/results/latest.json and update EVALS.md.
"""
from pathlib import Path


def main() -> None:
    tasks = sorted(Path(__file__).parent.joinpath("tasks").glob("*.yaml"))
    print(f"Found {len(tasks)} eval task(s). Runner not implemented yet.")


if __name__ == "__main__":
    main()
