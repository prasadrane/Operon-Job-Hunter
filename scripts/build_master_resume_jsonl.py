#!/usr/bin/env python3
"""Convert MASTER_RESUME.md + CareerGraph knowledge graph → JSONL (RAG chunks + graph entities/edges).

Usage:
    python scripts/build_master_resume_jsonl.py

Output: data/MASTER_RESUME.jsonl
Each line: {"type": str, "id": str, "content": str, "metadata": dict}
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_builder():
    """Import CareerGraphBuilder via importlib (digit-prefixed package)."""
    mod = importlib.import_module("src.pipeline.3_tailoring.career_graph_builder")
    return mod.CareerGraphBuilder


MASTER_PATH = ROOT / "data" / "MASTER_RESUME.md"
OUTPUT_PATH = ROOT / "data" / "MASTER_RESUME.jsonl"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:80] or "node"


def parse_resume_md(text: str) -> List[Dict[str, Any]]:
    """Extract semantic RAG chunks from the master resume markdown."""
    chunks: List[Dict[str, Any]] = []
    lines = text.splitlines()

    # --- Contact block (lines 1-9 before first ##) ---
    contact_lines = []
    for line in lines:
        if line.startswith("## "):
            break
        contact_lines.append(line)
    contact = "\n".join(contact_lines).strip()
    if contact:
        chunks.append({
            "type": "contact",
            "id": "contact_main",
            "content": contact,
            "metadata": {"section": "header", "name": "Alex Rivera"},
        })

    # --- Summaries ---
    summary_block = []
    in_summary = False
    for line in lines:
        if line.startswith("## ") and "summar" in line.lower():
            in_summary = True
            continue
        if in_summary and line.startswith("## "):
            break
        if in_summary:
            summary_block.append(line)

    # Canonical summary
    canon_match = re.search(r"###\s*Canonical Summary\s*\n(.*?)(?=\n###|\n##|\Z)", "\n".join(summary_block), re.S)
    if canon_match:
        chunks.append({
            "type": "summary",
            "id": "summary_canonical",
            "content": canon_match.group(1).strip(),
            "metadata": {"variant": "canonical"},
        })

    # Domain variants
    for m in re.finditer(r"-\s*\*\*([^*]+)\*\*:\s*(.+?)(?=\n- \*\*|\n##|\n###|\Z)", "\n".join(summary_block), re.S):
        variant_name = m.group(1).strip()
        body = m.group(2).strip()
        chunks.append({
            "type": "summary_variant",
            "id": f"summary_variant_{slug(variant_name)}",
            "content": f"**{variant_name}**: {body}",
            "metadata": {"variant": variant_name},
        })

    # --- Skills (7 categories) ---
    skills_block = []
    in_skills = False
    for line in lines:
        if line.startswith("## ") and "skill" in line.lower():
            in_skills = True
            continue
        if in_skills and line.startswith("## "):
            break
        if in_skills:
            skills_block.append(line)

    for m in re.finditer(r"-\s*\*\*([^*]+)\*\*:\s*(.+)", "\n".join(skills_block)):
        cat = m.group(1).strip()
        items = m.group(2).strip()
        chunks.append({
            "type": "skill_category",
            "id": f"skill_{slug(cat)}",
            "content": f"**{cat}**: {items}",
            "metadata": {"category": cat, "items": [i.strip() for i in items.split(",")]},
        })

    # --- Jobs, Stories, Projects, Education, Certifications ---
    current_company = ""
    current_role = ""
    current_story = ""
    story_bullets: List[str] = []
    job_meta: Dict[str, Any] = {}

    def flush_story():
        nonlocal current_story, story_bullets
        if current_story and story_bullets:
            chunks.append({
                "type": "story",
                "id": f"story_{slug(current_story)}",
                "content": f"### {current_story}\n\n" + "\n".join(f"- {b}" for b in story_bullets),
                "metadata": {
                    "company": current_company,
                    "role": current_role,
                    "story_title": current_story,
                    **job_meta,
                },
            })
        story_bullets = []
        current_story = ""

    in_experience = False
    in_projects = False
    in_education = False
    in_cert = False
    edu_lines: List[str] = []
    cert_lines: List[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("## "):
            header = line.lower()
            flush_story()
            in_experience = "experience" in header or "story" in header
            in_projects = "project" in header
            in_education = "education" in header
            in_cert = "certification" in header
            i += 1
            continue

        if in_cert and line.startswith("- "):
            cert_lines.append(line.lstrip("- ").strip())
            i += 1
            continue

        if in_education and line.startswith("- "):
            edu_lines.append(line.lstrip("- ").strip())
            i += 1
            continue

        if in_experience:
            # Company/Role line
            clean = line.replace(" - ", " - ").replace("-", " - ").replace(" - ", " - ").replace("-", " - ")
            clean_h = re.sub(r"^#+\s*", "", clean).replace("*", "").strip()
            if line.startswith("### ") and " - " in clean and not clean_h.lower().startswith("story"):
                flush_story()
                parts = re.split(r"\s*-\s*", clean_h, maxsplit=1)
                if len(parts) == 2:
                    current_role = parts[0].strip()
                    current_company = parts[1].strip()
                    job_meta = {"role": current_role, "company": current_company}
                i += 1
                continue

            # Story header (#### Story N - ...) or project (### Name)
            if line.startswith("#### ") or (line.startswith("### ") and "story" in line.lower()):
                flush_story()
                title = re.sub(r"^#+\s*", "", line).replace("*", "").strip()
                current_story = title
                i += 1
                continue

            # Bullet
            if line.startswith(("- ", "* ", "• ")) and current_story:
                story_bullets.append(line.lstrip("*-• ").strip())
                i += 1
                continue

        if in_projects and line.startswith("### "):
            flush_story()
            title = re.sub(r"^#+\s*", "", line).replace("*", "").strip()
            proj_bullets = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## ") and not lines[j].startswith("### "):
                if lines[j].startswith(("- ", "* ")):
                    proj_bullets.append(lines[j].lstrip("*- ").strip())
                j += 1
            chunks.append({
                "type": "project",
                "id": f"project_{slug(title)}",
                "content": f"### {title}\n\n" + "\n".join(f"- {b}" for b in proj_bullets),
                "metadata": {"title": title},
            })
            i = j
            continue

        i += 1

    flush_story()

    # Education
    for e in edu_lines:
        chunks.append({
            "type": "education",
            "id": f"edu_{slug(e[:40])}",
            "content": e,
            "metadata": {"raw": e},
        })

    # Certifications
    for c in cert_lines:
        chunks.append({
            "type": "certification",
            "id": f"cert_{slug(c[:40])}",
            "content": c,
            "metadata": {"raw": c},
        })

    return chunks


def build_graph_chunks(text: str) -> List[Dict[str, Any]]:
    """Build CareerGraph knowledge graph → JSONL chunks (nodes + edges)."""
    CareerGraphBuilder = _load_builder()
    builder = CareerGraphBuilder()
    graph = builder.build_from_text(text)

    chunks: List[Dict[str, Any]] = []

    # Nodes
    for node, data in graph.nodes(data=True):
        node_type = data.get("type", "Unknown")
        chunks.append({
            "type": "graph_node",
            "id": f"node_{slug(node)}",
            "content": data.get("bullet") or data.get("text") or data.get("name", node),
            "metadata": {
                "graph_node_id": node,
                "node_type": node_type,
                "name": data.get("name", node),
                "company": data.get("company"),
                "role": data.get("role"),
                "start_year": data.get("start_year"),
                "end_year": data.get("end_year"),
                "recency_score": data.get("recency_score"),
                "category": data.get("category"),
                "section_type": data.get("section_type"),
                "value": data.get("value"),
                "aliases": data.get("aliases"),
                "bullets_count": len(data.get("bullets", [])) if data.get("bullets") else None,
                "in_degree": graph.in_degree(node),
                "out_degree": graph.out_degree(node),
            },
        })

    # Edges
    for u, v, data in graph.edges(data=True):
        chunks.append({
            "type": "graph_edge",
            "id": f"edge_{slug(u)}__{slug(v)}__{slug(data.get('relation', 'LINK'))}",
            "content": f"{u} --[{data.get('relation', 'LINK')}]--> {v}",
            "metadata": {
                "source": u,
                "target": v,
                "relation": data.get("relation", "LINK"),
            },
        })

    return chunks


def main() -> int:
    import argparse
    from src.core.config import get_settings
    s = get_settings()

    parser = argparse.ArgumentParser(description="Build MASTER_RESUME.jsonl from markdown.")
    parser.add_argument("--profile-dir", default=None, help="Path to profile directory")
    args = parser.parse_args()

    if args.profile_dir:
        master_path = Path(args.profile_dir) / "MASTER_RESUME.md"
        output_path = Path(args.profile_dir) / "MASTER_RESUME.jsonl"
    else:
        master_path = s.master_resume_md_path
        output_path = s.master_resume_jsonl_path

    if not master_path.exists():
        print(f"ERROR: {master_path} not found", file=sys.stderr)
        return 1

    text = master_path.read_text(encoding="utf-8")

    resume_chunks = parse_resume_md(text)
    print(f"Parsed {len(resume_chunks)} resume chunks")

    try:
        graph_chunks = build_graph_chunks(text)
        graph_nodes = sum(1 for c in graph_chunks if c["type"] == "graph_node")
        graph_edges = sum(1 for c in graph_chunks if c["type"] == "graph_edge")
        print(f"Graph: {graph_nodes} nodes, {graph_edges} edges")
    except Exception as e:
        print(f"WARNING: Graph build failed ({e}), emitting resume chunks only", file=sys.stderr)
        graph_chunks = []

    all_chunks = resume_chunks + graph_chunks

    with output_path.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            # Strip None values from metadata
            chunk["metadata"] = {k: v for k, v in chunk["metadata"].items() if v is not None}
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"Wrote {len(all_chunks)} lines -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
