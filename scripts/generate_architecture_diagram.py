"""Generate CareerGraph-AI System Architecture Diagram using programmatic SVG + Playwright render."""

from __future__ import annotations
import math
import os
from pathlib import Path
import subprocess
import sys

# Output paths
ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
DOCS_DIR.mkdir(exist_ok=True)
SVG_OUT = DOCS_DIR / "architecture_diagram.svg"
PNG_OUT = DOCS_DIR / "architecture_diagram.png"

W, H = 1600, 1020  # viewBox dimensions

# Theme tokens
INK = "#0f172a"
MUTED = "#64748b"
SURFACE = "#ffffff"
BAND_BORDER = "#e2e8f0"

# Layer style: (stroke_color, band_tint, band_label)
LAYER_STYLE = {
    "L1": ("#2563eb", "#eff6ff", "1. INTERFACE & HUMAN-IN-THE-LOOP CHANNELS"),
    "L2": ("#059669", "#ecfdf5", "2. MACRO ORCHESTRATION & STATE MACHINE (LANGGRAPH)"),
    "L3": ("#b45309", "#fffbeb", "3. SPECIALIZED MICRO-AGENTS & ENGINES"),
    "L4": ("#7c3aed", "#f5f3ff", "4. REASONING ENGINE & COMPILER GATES"),
    "L5": ("#0284c7", "#f0f9ff", "5. 3-TIER OS MEMORY & PERSISTENT DATA STORES"),
}

# Edge kind colors
EDGE_STYLE = {
    "req": "#475569",
    "llm": "#b45309",
    "write": "#6d28d9",
    "read": "#0369a1",
}

FONT = "Segoe UI, system-ui, -apple-system, sans-serif"
FS_TITLE, FS_SUB, FS_EDGE, FS_BAND, FS_LEGEND = 15, 12, 11, 13, 12

# Boxes: id -> (x, y, w, h, layer, kind, title, sub)
BOXES = {
    # L1: Interface (y: 110-210)
    "web_ui": (80, 115, 430, 95, "L1", "box", "Mission Control 2.0 (Web & D3)", "FastAPI REST + Live SSE Telemetry + D3 Graph"),
    "cli_main": (550, 115, 430, 95, "L1", "box", "Unified CLI Controller", "Daemon, Scanner, Evaluator & Playwright Submitter"),
    "telegram_hitl": (1020, 115, 480, 95, "L1", "box", "Telegram HITL Approval Bot", "Interactive Cards, PDF Previews & Approval Signals"),

    # L2: Orchestration (y: 290-390)
    "langgraph_dag": (80, 295, 430, 95, "L2", "box", "LangGraph StateGraph DAG", "5-Stage Typed Pipeline & Conditional Routing"),
    "circuit_breaker": (550, 295, 430, 95, "L2", "box", "Execution Circuit Breakers", "Bounded Worker Threads, 45s Timeout Budgets"),
    "hitl_gate": (1020, 295, 480, 95, "L2", "box", "Dynamic interrupt() Gate", "Pre-Submission Checkpoint & Command(resume) Engine"),

    # L3: Micro-Agents (y: 470-570)
    "discovery_squad": (70, 475, 335, 95, "L3", "box", "Discovery Squad (9 Crawlers)", "Deferred Tool Search & USCIS H-1B Verification"),
    "eval_guard": (435, 475, 335, 95, "L3", "box", "7-Block Evaluator & Work Auth", "Multi-Model Consensus Voting & Ghost-Job Filter"),
    "tailor_optimizer": (800, 475, 335, 95, "L3", "box", "GraphRAG Evaluator-Optimizer", "3-Persona Critic & Surgical Delta Patching"),
    "websurfer_sub": (1165, 475, 355, 95, "L3", "box", "WebSurfer Agent & FastPath", "AXTree + Set-of-Marks, Quiescence & Form Healing"),

    # L4: Gateway & Compiler (y: 645-745)
    "llm_gateway": (80, 645, 780, 105, "L4", "box", "LLM Gateway & Model Tiering Router", "Tiered Routing: Gemini Flash (S1/2/4) & Gemini Pro (S3)"),
    "pdf_compiler": (900, 645, 620, 105, "L4", "dashed", "Deterministic Compiler & Page Gate", "ReportLab / Typst Engine + Strict 1-Page / 2-Page Layout Bounds"),

    # L5: 3-Tier OS Memory (y: 845-965)
    "core_mem": (70, 845, 340, 120, "L5", "cyl", "Core Memory (In-Context RAM)", "Candidate Constraints, Floor Salary & Dynamic Tool API"),
    "recall_mem": (440, 845, 340, 120, "L5", "cyl", "Recall Memory (SQLite Ledger)", "Append-Only Applications, Q&A Cache, SqliteSaver WAL"),
    "archival_mem": (810, 845, 340, 120, "L5", "cyl", "Archival Memory (GraphRAG)", "NetworkX Knowledge Graph, STAR Stories & Impact Metrics"),
    "browser_profile": (1180, 845, 340, 120, "L5", "cyl", "Playwright Browser Profile", "Persistent Session Cookies, Storage State & Evasions"),
}

# Chips inside llm_gateway
CHIPS = [
    (100, 710, 160, 28, "Gemini 2.5 Flash", "Low-Latency Tier"),
    (280, 710, 160, 28, "Gemini 2.5 Pro", "Deep Reasoning Tier"),
    (460, 710, 160, 28, "Qwen 2.5 72B", "Alibaba Open Gateway"),
    (640, 710, 180, 28, "OpenRouter / DeepSeek", "Multi-Provider Fallback"),
]

# Bands: (layer, y_top, y_bot)
BANDS = [
    ("L1", 75, 230),
    ("L2", 255, 410),
    ("L3", 435, 590),
    ("L4", 615, 770),
    ("L5", 795, 990),
]

# Legend: (kind, label)
LEGEND = [
    ("req", "Control & State Flow"),
    ("llm", "Tiered LLM / Reasoning"),
    ("write", "State Snapshot / Write"),
    ("read", "GraphRAG / Read Query"),
]

LABEL_ANCHORS = {}

# Edges: (src, dst, kind, label, (lx, ly), [(x1,y1), (x2,y2), ...])
EDGES = [
    # L1 -> L2
    ("web_ui", "langgraph_dag", "req", "invoke pipeline", (295, 250), [(295, 210), (295, 295)]),
    ("cli_main", "circuit_breaker", "req", "CLI batch run", (765, 250), [(765, 210), (765, 295)]),
    ("hitl_gate", "telegram_hitl", "req", "interrupt() alert", (1260, 250), [(1260, 295), (1260, 210)]),

    # L2 -> L3
    ("langgraph_dag", "discovery_squad", "req", "Stage 1", (180, 435), [(180, 390), (180, 475)]),
    ("langgraph_dag", "eval_guard", "req", "Stage 2", (510, 435), [(350, 390), (350, 430), (510, 430), (510, 475)]),
    ("circuit_breaker", "tailor_optimizer", "req", "Stage 3 (bounded)", (920, 435), [(820, 390), (820, 430), (920, 430), (920, 475)]),
    ("hitl_gate", "websurfer_sub", "req", "Stage 4 (approved)", (1340, 435), [(1340, 390), (1340, 475)]),

    # L3 -> L4
    ("eval_guard", "llm_gateway", "llm", "consensus vote", (480, 608), [(540, 570), (540, 645)]),
    ("tailor_optimizer", "llm_gateway", "llm", "evaluator-optimizer", (720, 608), [(850, 570), (850, 605), (680, 605), (680, 645)]),
    ("tailor_optimizer", "pdf_compiler", "write", "compile AST", (1100, 608), [(950, 570), (950, 605), (1150, 605), (1150, 645)]),

    # L3/L4 -> L5 (Data Stores)
    ("discovery_squad", "core_mem", "read", "verify H-1B", (130, 810), [(130, 570), (130, 845)]),
    ("eval_guard", "recall_mem", "write", "persist score", (610, 810), [(610, 570), (610, 845)]),
    ("tailor_optimizer", "archival_mem", "read", "Multi-Hop GraphRAG", (980, 810), [(980, 570), (980, 845)]),
    ("websurfer_sub", "browser_profile", "read", "session cookies", (1350, 810), [(1350, 570), (1350, 845)]),
]




def esc(s: str) -> str:
    """XML character escaping."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def emit_svg() -> str:
    """Generate professional hand-crafted SVG diagram."""
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="background-color: {SURFACE}; font-family: {FONT};">',
        "  <defs>",
        '    <marker id="arrow-req" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        f'      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="{EDGE_STYLE["req"]}" />',
        "    </marker>",
        '    <marker id="arrow-llm" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        f'      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="{EDGE_STYLE["llm"]}" />',
        "    </marker>",
        '    <marker id="arrow-write" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        f'      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="{EDGE_STYLE["write"]}" />',
        "    </marker>",
        '    <marker id="arrow-read" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        f'      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="{EDGE_STYLE["read"]}" />',
        "    </marker>",
        '    <filter id="shadow" x="-5%" y="-5%" width="110%" height="115%" filterUnits="userSpaceOnUse">',
        '      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.06"/>',
        "    </filter>",
        "  </defs>",
        "",
        "  <!-- DIAGRAM TITLE -->",
        f'  <text x="80" y="42" font-size="22" font-weight="800" fill="{INK}" letter-spacing="-0.5px">CareerGraph-AI — System Architecture &amp; Agentic Operating System</text>',
        f'  <text x="80" y="62" font-size="13" font-weight="500" fill="{MUTED}">Production Architecture: 5-Stage LangGraph DAG, 3-Tier OS Memory, AXTree Grounding &amp; Multi-Model Consensus</text>',
        "",
        "  <!-- LAYER SWIMLANES -->",
    ]

    # Render Bands
    for layer, yt, yb in BANDS:
        stroke, tint, label = LAYER_STYLE[layer]
        bh = yb - yt
        lines.append(f'  <!-- Band {layer} -->')
        lines.append(f'  <rect x="50" y="{yt}" width="{W-100}" height="{bh}" rx="12" fill="{tint}" stroke="{BAND_BORDER}" stroke-width="1.2" />')
        lines.append(f'  <text x="75" y="{yt + 20}" font-size="{FS_BAND}" font-weight="700" fill="{stroke}" letter-spacing="0.5px">{esc(label)}</text>')

    lines.append("")
    lines.append("  <!-- EDGES / CONNECTIONS -->")

    # Render Edges
    for src, dst, kind, label, (lx, ly), poly in EDGES:
        color = EDGE_STYLE[kind]
        marker = f"arrow-{kind}"
        pts = " ".join(f"{x},{y}" for x, y in poly)
        dash = ' stroke-dasharray="5,4"' if kind == "read" else ""
        lines.append(f'  <polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"{dash} marker-end="url(#{marker})" />')
        if label:
            anchor = LABEL_ANCHORS.get((src, dst), "middle")
            lines.append(f'  <rect x="{lx - 60}" y="{ly - 10}" width="120" height="18" rx="4" fill="{SURFACE}" opacity="0.92"/>')
            lines.append(f'  <text x="{lx}" y="{ly + 3}" font-size="{FS_EDGE}" font-weight="600" font-style="italic" fill="{color}" text-anchor="{anchor}">{esc(label)}</text>')

    lines.append("")
    lines.append("  <!-- COMPONENT BOXES -->")

    # Render Boxes
    for bid, (bx, by, bw, bh, layer, kind, title, sub) in BOXES.items():
        stroke, tint, _ = LAYER_STYLE[layer]
        if kind == "cyl":
            # Cylinder representation
            eh = 14
            lines.append(f'  <!-- Cylinder {bid} -->')
            lines.append(f'  <g filter="url(#shadow)">')
            lines.append(f'    <rect x="{bx}" y="{by + eh}" width="{bw}" height="{bh - eh}" rx="6" fill="{SURFACE}" stroke="{stroke}" stroke-width="1.8" />')
            lines.append(f'    <ellipse cx="{bx + bw/2}" cy="{by + bh}" rx="{bw/2}" ry="{eh}" fill="{SURFACE}" stroke="{stroke}" stroke-width="1.8" />')
            lines.append(f'    <ellipse cx="{bx + bw/2}" cy="{by + eh}" rx="{bw/2}" ry="{eh}" fill="{tint}" stroke="{stroke}" stroke-width="1.8" />')
            lines.append(f'  </g>')
            lines.append(f'  <text x="{bx + bw/2}" y="{by + 48}" font-size="{FS_TITLE}" font-weight="700" fill="{INK}" text-anchor="middle">{esc(title)}</text>')
            lines.append(f'  <text x="{bx + bw/2}" y="{by + 72}" font-size="{FS_SUB}" font-weight="500" fill="{MUTED}" text-anchor="middle">{esc(sub)}</text>')
        else:
            dash = ' stroke-dasharray="6,4"' if kind == "dashed" else ""
            lines.append(f'  <!-- Box {bid} -->')
            lines.append(f'  <rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="10" fill="{SURFACE}" stroke="{stroke}" stroke-width="1.8"{dash} filter="url(#shadow)" />')
            ty = by + 32 if bid == "llm_gateway" else by + 38
            sy = by + 52 if bid == "llm_gateway" else by + 62
            lines.append(f'  <text x="{bx + bw/2}" y="{ty}" font-size="{FS_TITLE}" font-weight="700" fill="{INK}" text-anchor="middle">{esc(title)}</text>')
            lines.append(f'  <text x="{bx + bw/2}" y="{sy}" font-size="{FS_SUB}" font-weight="500" fill="{MUTED}" text-anchor="middle">{esc(sub)}</text>')

    # Render Chips inside llm_gateway
    lines.append("")
    lines.append("  <!-- LLM GATEWAY CHIPS -->")
    for cx, cy, cw, ch, ctitle, csub in CHIPS:
        lines.append(f'  <rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="6" fill="#f5f3ff" stroke="#7c3aed" stroke-width="1.2" />')
        lines.append(f'  <text x="{cx + cw/2}" y="{cy + 14}" font-size="11" font-weight="700" fill="#6d28d9" text-anchor="middle">{esc(ctitle)}</text>')
        lines.append(f'  <text x="{cx + cw/2}" y="{cy + 24}" font-size="9" font-weight="500" fill="{MUTED}" text-anchor="middle">{esc(csub)}</text>')

    # Render Legend in Top-Right (2x2 Grid)
    lines.append("")
    lines.append("  <!-- LEGEND (2x2 Grid) -->")
    leg_x, leg_y, leg_w, leg_h = 1060, 12, 490, 56
    lines.append(f'  <rect x="{leg_x}" y="{leg_y}" width="{leg_w}" height="{leg_h}" rx="8" fill="{SURFACE}" stroke="{BAND_BORDER}" stroke-width="1.2" filter="url(#shadow)" />')
    legend_items = [
        ("req", "Control & State Flow", 0, 0),
        ("llm", "Tiered LLM Call", 1, 0),
        ("write", "State Snapshot / Write", 0, 1),
        ("read", "GraphRAG / Read Query", 1, 1),
    ]
    for k, ltext, col, row in legend_items:
        lx = leg_x + 16 + (col * 235)
        ly = leg_y + 20 + (row * 24)
        color = EDGE_STYLE[k]
        dash = ' stroke-dasharray="4,3"' if k == "read" else ""
        lines.append(f'  <line x1="{lx}" y1="{ly}" x2="{lx + 20}" y2="{ly}" stroke="{color}" stroke-width="2.2"{dash} />')
        lines.append(f'  <text x="{lx + 26}" y="{ly + 4}" font-size="{FS_LEGEND}" font-weight="600" fill="{INK}">{esc(ltext)}</text>')

    lines.append("</svg>")
    return "\n".join(lines)



def main():
    svg_content = emit_svg()
    SVG_OUT.write_text(svg_content, encoding="utf-8")
    print(f"[OK] SVG generated: {SVG_OUT}")

    # Render PNG using Playwright
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
            page.set_content(svg_content)
            page.screenshot(path=str(PNG_OUT))
            browser.close()
        print(f"[OK] PNG rendered: {PNG_OUT}")
    except Exception as exc:
        print(f"[WARN] Playwright rendering skipped or failed: {exc}")


if __name__ == "__main__":
    main()

