"""QA verification script for COM-367."""
import os
import tempfile
from envault.cli import app
from typer.testing import CliRunner

runner = CliRunner()

# Test 1: DB_PASSWORD with *** (defect says this should be exit_code=1)
print("=== Root Cause 1: DB_PASSWORD=*** ===")
with tempfile.TemporaryDirectory() as td:
    env_file = os.path.join(td, ".env")
    with open(env_file, "w") as f:
        f.write("DB_PASSWORD=***\n")
    result = runner.invoke(app, ["scan", env_file, "--no-permissions", "--no-gitignore"])
    print(f"  EXIT_CODE: {result.exit_code}")
    print(f"  HAS_weak_secret: {'weak_secret' in result.output}")
    print(f"  OUTPUT: {result.output.strip()}")
    print()

# Test 2: AKIA key (current test value)
print("=== Root Cause 2: AKIAIO...MPLE ===")
with tempfile.TemporaryDirectory() as td:
    env_file = os.path.join(td, ".env")
    with open(env_file, "w") as f:
        f.write("AWS_ACCESS_KEY_ID=AKIAIO...MPLE\n")
    result = runner.invoke(app, ["scan", env_file, "--no-permissions", "--no-gitignore"])
    print(f"  EXIT_CODE: {result.exit_code}")
    print(f"  HAS_hardcoded_credential: {'hardcoded_credential' in result.output}")
    print(f"  OUTPUT: {result.output.strip()}")
    print()

# Test 3: JSON output with Rich control chars
print("=== Root Cause 3: JSON output control chars ===")
import json as _json

with tempfile.TemporaryDirectory() as td:
    env_file = os.path.join(td, ".env")
    with open(env_file, "w") as f:
        f.write("AWS_ACCESS_KEY_ID=AKIAIO...MPLE\n")
    result = runner.invoke(app, ["scan", env_file, "--json", "--no-permissions", "--no-gitignore"])
    try:
        parsed = _json.loads(result.output)
        print(f"  JSON parse: OK (list of {len(parsed)} entries)")
    except _json.JSONDecodeError as e:
        print(f"  JSON parse: FAILED - {e}")
        # Try with strict=False
        try:
            parsed = _json.loads(result.output, strict=False)
            print("  JSON parse (strict=False): OK")
        except _json.JSONDecodeError as e2:
            print(f"  JSON parse (strict=False): FAILED - {e2}")
            print(f"  Raw output repr: {result.output[:200]!r}")
    print()

# Test 4: What severity does DB_PASSWORD=password actually get?
print("=== Root Cause 1b: DB_PASSWORD=password severity ===")
with tempfile.TemporaryDirectory() as td:
    env_file = os.path.join(td, ".env")
    with open(env_file, "w") as f:
        f.write("DB_PASSWORD=password\n")
    result = runner.invoke(app, ["scan", env_file, "--no-permissions", "--no-gitignore"])
    print(f"  EXIT_CODE: {result.exit_code}")
    print(f"  HAS_weak_secret: {'weak_secret' in result.output}")
    print(f"  OUTPUT: {result.output.strip()}")
    print()

# Test 5: The original defect test value AKIAIO5VESWPEXAMPLE
print("=== Root Cause 2b: AKIAIO5VESWPEXAMPLE (15 chars after AKIA) ===")
with tempfile.TemporaryDirectory() as td:
    env_file = os.path.join(td, ".env")
    with open(env_file, "w") as f:
        f.write("AWS_ACCESS_KEY_ID=AKIAIO5VESWPEXAMPLE\n")
    result = runner.invoke(app, ["scan", env_file, "--no-permissions", "--no-gitignore"])
    print(f"  EXIT_CODE: {result.exit_code}")
    print(f"  HAS_hardcoded_credential: {'hardcoded_credential' in result.output}")
    print(f"  OUTPUT: {result.output.strip()}")
