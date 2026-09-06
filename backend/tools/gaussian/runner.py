import subprocess


def run_gaussian(input_file: str, output_file: str) -> str:
    """Execute Gaussian via subprocess."""
    result = subprocess.run(
        ["g16", input_file],
        capture_output=True,
        text=True,
    )
    return result.stdout
