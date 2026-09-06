import subprocess


def run_multiwfn(input_file: str, commands: str) -> str:
    """Execute Multiwfn with piped commands."""
    result = subprocess.run(
        ["multiwfn", input_file],
        input=commands,
        capture_output=True,
        text=True,
    )
    return result.stdout
