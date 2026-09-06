import subprocess


def run_eqv2(input_file: str, output_file: str) -> str:
    """Execute EqV2 via subprocess."""
    result = subprocess.run(
        ["eqv2", input_file, "-o", output_file],
        capture_output=True,
        text=True,
    )
    return result.stdout
