"""Validate all careers URLs in companies.yaml by actually hitting the endpoints."""

import asyncio
import importlib
import sys
from pathlib import Path
import yaml
import httpx

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Dynamic import for numbered module
_portal_mod = importlib.import_module("src.pipeline.1_discovery.portal_crawler")


async def validate_company(company: dict, client: httpx.AsyncClient) -> dict:
    """Validate a single company's careers endpoint."""
    name = company["name"]
    portal_type = company["portal_type"]
    board_token = company["board_token"]
    careers_url = company.get("careers_url", "")

    result = {
        "name": name,
        "portal_type": portal_type,
        "board_token": board_token,
        "careers_url": careers_url,
        "status": "unknown",
        "jobs_found": 0,
        "error": None,
    }

    try:
        if portal_type == "greenhouse":
            url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                result["jobs_found"] = len(data.get("jobs", []))
                result["status"] = "ok"
            else:
                result["status"] = "failed"
                result["error"] = f"HTTP {resp.status_code}"

        elif portal_type == "lever":
            url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                result["jobs_found"] = len(data) if isinstance(data, list) else 0
                result["status"] = "ok"
            else:
                result["status"] = "failed"
                result["error"] = f"HTTP {resp.status_code}"

        elif portal_type == "ashby":
            # Try REST API first (more reliable)
            url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}?includeCompensation=true"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                jobs = data.get("jobs", []) or data.get("results", [])
                result["jobs_found"] = len(jobs)
                result["status"] = "ok"
            else:
                # Try GraphQL fallback
                graphql_url = "https://jobs.ashbyhq.com/api/non-app-graphql-endpoint"
                query = {
                    "operationName": "ApiJobBoardWithTeams",
                    "variables": {"organizationHostedJobsPageName": board_token},
                    "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id } } }",
                }
                resp = await client.post(graphql_url, json=query)
                if resp.status_code == 200:
                    data = resp.json()
                    postings = data.get("data", {}).get("jobBoard", {}).get("jobPostings", [])
                    result["jobs_found"] = len(postings)
                    result["status"] = "ok"
                else:
                    result["status"] = "failed"
                    result["error"] = f"HTTP {resp.status_code}"

        elif portal_type == "workday":
            # Extract tenant and board from careers_url
            import re
            match = re.search(r"https://([a-zA-Z0-9_-]+)\.(wd\d+\.)?myworkdayjobs\.com/([a-zA-Z0-9_-]+)", careers_url)
            if match:
                tenant = match.group(1)
                wd_instance = match.group(2).rstrip(".") if match.group(2) else "wd1"
                board = match.group(3)
                url = f"https://{tenant}.{wd_instance}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"
                payload = {"appliedFacets": {}, "limit": 1, "offset": 0}
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    result["jobs_found"] = len(data.get("jobPostings", []))
                    result["status"] = "ok"
                else:
                    result["status"] = "failed"
                    result["error"] = f"HTTP {resp.status_code}"
            else:
                result["status"] = "failed"
                result["error"] = "Invalid Workday URL format"

        elif portal_type == "smartrecruiters":
            url = f"https://api.smartrecruiters.com/v1/companies/{board_token}/postings?limit=1&offset=0&status=PUBLIC"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                result["jobs_found"] = len(data.get("content", []))
                result["status"] = "ok"
            else:
                result["status"] = "failed"
                result["error"] = f"HTTP {resp.status_code}"

        elif portal_type in ("amazon", "microsoft", "google"):
            # These are big tech with custom APIs - just check if the domain responds
            if portal_type == "amazon":
                url = "https://www.amazon.jobs/en/search.json?category[]=software-development&result_type=jobs"
            elif portal_type == "microsoft":
                url = "https://gcsservices.careers.microsoft.com/search/api/v1/search?q=Software&pg=1&pgSz=1"
            else:  # google
                url = "https://careers.google.com/api/v3/search/?q=Software&page_size=1"

            resp = await client.get(url)
            if resp.status_code == 200:
                result["status"] = "ok"
                result["jobs_found"] = -1  # Unknown count
            else:
                result["status"] = "failed"
                result["error"] = f"HTTP {resp.status_code}"

        else:
            result["status"] = "skipped"
            result["error"] = f"Unknown portal type: {portal_type}"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


async def main():
    """Validate all companies in companies.yaml."""
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    from src.core.config import get_settings
    companies_file = get_settings().companies_yaml_path

    with open(companies_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    companies = data.get("companies", [])
    print(f"Validating {len(companies)} companies...\n")

    results = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        tasks = [validate_company(c, client) for c in companies]
        results = await asyncio.gather(*tasks)

    # Print results
    ok_count = sum(1 for r in results if r["status"] == "ok")
    failed_count = sum(1 for r in results if r["status"] in ("failed", "error"))
    skipped_count = sum(1 for r in results if r["status"] == "skipped")

    print("=" * 80)
    print(f"RESULTS: {ok_count} OK, {failed_count} FAILED, {skipped_count} SKIPPED")
    print("=" * 80)

    if ok_count > 0:
        print(f"\n[OK] WORKING ({ok_count}):")
        for r in results:
            if r["status"] == "ok":
                jobs_str = f"{r['jobs_found']} jobs" if r["jobs_found"] >= 0 else "OK"
                print(f"  {r['name']:25} [{r['portal_type']:15}] {jobs_str}")

    if failed_count > 0:
        print(f"\n[FAIL] FAILED ({failed_count}):")
        for r in results:
            if r["status"] in ("failed", "error"):
                print(f"  {r['name']:25} [{r['portal_type']:15}] {r['error']}")
                print(f"    URL: {r['careers_url']}")

    if skipped_count > 0:
        print(f"\n[SKIP] SKIPPED ({skipped_count}):")
        for r in results:
            if r["status"] == "skipped":
                print(f"  {r['name']:25} [{r['portal_type']:15}] {r['error']}")

    # Write report
    report_file = Path(__file__).parent.parent / "data" / "validation_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"Validation Report - {len(companies)} companies\n")
        f.write(f"OK: {ok_count}, FAILED: {failed_count}, SKIPPED: {skipped_count}\n\n")

        f.write("WORKING:\n")
        for r in results:
            if r["status"] == "ok":
                f.write(f"  {r['name']} [{r['portal_type']}] - {r['jobs_found']} jobs\n")

        f.write("\nFAILED:\n")
        for r in results:
            if r["status"] in ("failed", "error"):
                f.write(f"  {r['name']} [{r['portal_type']}] - {r['error']}\n")
                f.write(f"    {r['careers_url']}\n")

    print(f"\nReport saved to: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())
