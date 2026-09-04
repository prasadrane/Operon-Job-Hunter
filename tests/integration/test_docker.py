#!/usr/bin/env python3
"""Smoke tests for Docker artifacts (Task 1).

Tests:
  1. Dockerfile builds successfully
  2. Image size < 1GB
  3. Container starts and /api/health returns 200
  4. docker-compose.yml syntax is valid
  5. .dockerignore exists and excludes key paths

Usage: python tests/integration/test_docker.py
Requires: docker, docker-compose (or docker compose plugin)
"""

import json
import subprocess
import sys
import time

IMAGE_NAME = "careergraph-ai-test"
CONTAINER_NAME = "careergraph-ai-test-ctr"
COMPOSE_FILE = "docker-compose.yml"


def run(cmd, check=True, capture=True):
    """Run shell command, return stdout."""
    result = subprocess.run(
        cmd, shell=True, capture_output=capture, text=True
    )
    if check and result.returncode != 0:
        print(f"FAIL: {cmd}")
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()}")
        return None
    return result.stdout.strip() if capture else ""


def test_1_dockerfile_builds():
    """Test 1: Dockerfile builds successfully."""
    print("\n[Test 1] Dockerfile builds...")
    out = run(f"docker build -t {IMAGE_NAME} .")
    if out is None:
        print("  FAIL: build failed")
        return False
    print("  PASS")
    return True


def test_2_image_size():
    """Test 2: Image size < 1GB."""
    print("\n[Test 2] Image size < 1GB...")
    out = run(f"docker image inspect {IMAGE_NAME} --format='{{{{.Size}}}}'")
    if out is None:
        print("  FAIL: could not read image size")
        return False
    size_bytes = int(out.strip("'"))
    size_mb = size_bytes / (1024 * 1024)
    print(f"  Image size: {size_mb:.1f} MB")
    if size_mb > 1024:
        print(f"  FAIL: exceeds 1GB limit ({size_mb:.1f} MB)")
        return False
    print("  PASS")
    return True


def test_3_health_check():
    """Test 3: Container starts and /api/health returns 200."""
    print("\n[Test 3] Health check /api/health...")
    # Clean up any prior container
    run(f"docker rm -f {CONTAINER_NAME}", check=False)
    run(
        f"docker run -d --name {CONTAINER_NAME} -p 18765:8000 {IMAGE_NAME}",
        check=True,
    )
    # Wait for startup
    time.sleep(8)
    out = run(
        "curl -s -o /dev/null -w '%{http_code}' http://localhost:18765/api/health",
        check=False,
    )
    run(f"docker rm -f {CONTAINER_NAME}", check=False)
    if out and "200" in out:
        print("  PASS (HTTP 200)")
        return True
    print(f"  FAIL: got '{out}'")
    return False


def test_4_compose_syntax():
    """Test 4: docker-compose.yml syntax is valid."""
    print("\n[Test 4] docker-compose.yml syntax...")
    out = run(f"docker compose -f {COMPOSE_FILE} config --quiet", check=False)
    # docker compose returns 0 on valid; some versions need fallback
    if out is not None and out == "":
        proc = subprocess.run(
            f"docker compose -f {COMPOSE_FILE} config --quiet",
            shell=True, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            print("  PASS")
            return True
    # Fallback: just check YAML parses
    try:
        import yaml
        with open(COMPOSE_FILE) as f:
            yaml.safe_load(f)
        print("  PASS (YAML parse)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_5_dockerignore():
    """Test 5: .dockerignore exists and excludes key paths."""
    print("\n[Test 5] .dockerignore content...")
    try:
        with open(".dockerignore") as f:
            content = f.read()
        required = [".git", "tests/", "__pycache__", ".env", "data/"]
        missing = [p for p in required if p not in content]
        if missing:
            print(f"  FAIL: missing exclusions: {missing}")
            return False
        print("  PASS")
        return True
    except FileNotFoundError:
        print("  FAIL: .dockerignore not found")
        return False


def main():
    print("=" * 50)
    print("Docker Artifact Tests (Task 1)")
    print("=" * 50)

    results = {}
    results["dockerfile_builds"] = test_1_dockerfile_builds()
    if not results["dockerfile_builds"]:
        print("\nABORT: Dockerfile did not build, skipping remaining tests.")
        sys.exit(1)
    results["image_size_under_1gb"] = test_2_image_size()
    results["health_check"] = test_3_health_check()
    results["compose_syntax"] = test_4_compose_syntax()
    results["dockerignore"] = test_5_dockerignore()

    # Cleanup
    run(f"docker rmi -f {IMAGE_NAME}", check=False)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    failed = sum(1 for v in results.values() if not v)
    if failed:
        print(f"\n{failed} test(s) failed.")
        sys.exit(1)
    print("\nAll tests passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
