"""Generate thesis-ready visualizations for the LLM-CTF research project.

Outputs each figure as editable SVG, vector PDF, and 300-DPI PNG. Conceptual
figures are derived from the research proposal; result figures read the current
workspace CSV reports so their values are reproducible.
"""

from __future__ import annotations

import csv
import math
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"

NAVY = "#17324D"
BLUE = "#2F6B9A"
TEAL = "#2A9D8F"
ORANGE = "#E76F51"
GOLD = "#E9C46A"
PALE_BLUE = "#EAF2F8"
PALE_TEAL = "#E8F6F3"
PALE_ORANGE = "#FDEDE8"
PALE_GOLD = "#FFF6D9"
INK = "#1F2933"
MID = "#5D6D7E"
LIGHT = "#F5F7F9"
GRID = "#D9E1E8"
WHITE = "#FFFFFF"


plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "figure.facecolor": WHITE,
        "axes.facecolor": WHITE,
        "savefig.facecolor": WHITE,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    }
)


CAPTIONS: list[dict[str, str]] = []


def wrap(text: str, width: int = 24) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False))


def new_canvas(figsize=(7.2, 4.6)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def box(
    ax,
    x,
    y,
    w,
    h,
    text,
    *,
    fc=WHITE,
    ec=NAVY,
    lw=1.4,
    fontsize=10.5,
    weight="normal",
    color=INK,
    radius=0.018,
    zorder=2,
):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
        zorder=zorder,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight=weight,
        color=color,
        zorder=zorder + 1,
        linespacing=1.2,
    )
    return patch


def arrow(ax, start, end, *, color=MID, lw=1.5, style="-|>", connection="arc3"):
    a = FancyArrowPatch(
        start,
        end,
        arrowstyle=style,
        mutation_scale=12,
        linewidth=lw,
        color=color,
        connectionstyle=connection,
        shrinkA=2,
        shrinkB=2,
        zorder=1,
    )
    ax.add_patch(a)
    return a


def heading(ax, title: str, subtitle: str | None = None):
    ax.text(0.02, 0.97, title, ha="left", va="top", fontsize=14, fontweight="bold", color=NAVY)
    if subtitle:
        ax.text(0.02, 0.91, subtitle, ha="left", va="top", fontsize=9.5, color=MID)


def note(ax, text: str, x=0.02, y=0.025, ha="left"):
    ax.text(x, y, text, ha=ha, va="bottom", fontsize=8.5, color=MID, style="italic")


def save(fig, stem: str, caption: str, chapter: str, source: str, interpretation: str = ""):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf", "svg"):
        kwargs = {"bbox_inches": "tight", "pad_inches": 0.08}
        if ext == "png":
            kwargs["dpi"] = 300
        fig.savefig(OUT / f"{stem}.{ext}", **kwargs)
    plt.close(fig)
    CAPTIONS.append(
        {
            "stem": stem,
            "chapter": chapter,
            "caption": caption,
            "source": source,
            "interpretation": interpretation,
        }
    )


def fig_01_research_model():
    fig, ax = new_canvas((7.2, 4.8))
    heading(ax, "Conceptual model of LLM-enhanced continuous testing")
    ax.text(0.17, 0.84, "CURRENT CHALLENGES", ha="center", color=ORANGE, fontweight="bold")
    ax.text(0.50, 0.84, "LLM-CTF CAPABILITIES", ha="center", color=BLUE, fontweight="bold")
    ax.text(0.83, 0.84, "EXPECTED OUTCOMES", ha="center", color=TEAL, fontweight="bold")
    left = ["Brittle test scripts", "High maintenance effort", "Slow feedback loops", "Flaky / low-trust tests"]
    middle = ["Autonomous test generation", "Predictive test selection", "Self-healing support", "Explainable orchestration"]
    right = ["Higher test effectiveness", "Improved execution efficiency", "Greater reliability", "Faster developer feedback"]
    ys = [0.68, 0.54, 0.40, 0.26]
    for y, t in zip(ys, left):
        box(ax, 0.04, y, 0.26, 0.09, t, fc=PALE_ORANGE, ec=ORANGE, fontsize=9.5)
    for y, t in zip(ys, middle):
        box(ax, 0.37, y, 0.26, 0.09, t, fc=PALE_BLUE, ec=BLUE, fontsize=9.5)
    for y, t in zip(ys, right):
        box(ax, 0.70, y, 0.26, 0.09, t, fc=PALE_TEAL, ec=TEAL, fontsize=9.5)
    for y in ys:
        arrow(ax, (0.305, y + 0.045), (0.365, y + 0.045), color=BLUE)
        arrow(ax, (0.635, y + 0.045), (0.695, y + 0.045), color=TEAL)
    box(ax, 0.30, 0.075, 0.40, 0.075, "Safeguards: AST policy, repeated validation, rollback and audit trace", fc=PALE_GOLD, ec=GOLD, fontsize=8.6)
    arrow(ax, (0.50, 0.15), (0.50, 0.25), color=GOLD)
    save(
        fig,
        "figure_1_1_research_conceptual_model",
        "Conceptual model of LLM-enhanced continuous testing.",
        "Chapter 1 - Introduction",
        "Developed by the researcher from the proposal problem statement and objectives.",
        "The framework is expected to convert known continuous-testing bottlenecks into measurable effectiveness, efficiency and reliability outcomes, subject to governance safeguards.",
    )


def fig_02_rq_objective_mapping():
    fig, ax = new_canvas((7.2, 5.1))
    heading(ax, "Mapping of research questions, objectives and evaluation evidence")
    box(ax, 0.10, 0.79, 0.80, 0.12, wrap("Primary RQ: How can an integrated LLM-driven framework improve the effectiveness, efficiency and reliability of continuous testing in CI/CD pipelines?", 80), fc=PALE_BLUE, ec=NAVY, fontsize=10, weight="bold")
    box(ax, 0.05, 0.53, 0.40, 0.15, wrap("RQ1: How can LLMs improve continuous testing in CI/CD pipelines?", 42), fc=WHITE, ec=BLUE, fontsize=10)
    box(ax, 0.55, 0.53, 0.40, 0.15, wrap("RQ2: How effective is LLM-based predictive test selection compared with traditional methods?", 42), fc=WHITE, ec=TEAL, fontsize=10)
    box(ax, 0.05, 0.27, 0.40, 0.15, wrap("RO1: Design modular agents for test generation, predictive selection and self-healing.", 42), fc=PALE_BLUE, ec=BLUE, fontsize=10)
    box(ax, 0.55, 0.27, 0.40, 0.15, wrap("RO2: Empirically compare coverage, defect detection and execution efficiency.", 42), fc=PALE_TEAL, ec=TEAL, fontsize=10)
    box(ax, 0.19, 0.07, 0.62, 0.09, "Evidence: prototype behaviour + controlled traditional-versus-agentic experiment", fc=PALE_GOLD, ec=GOLD, fontsize=9.5)
    arrow(ax, (0.35, 0.79), (0.25, 0.69), color=BLUE)
    arrow(ax, (0.65, 0.79), (0.75, 0.69), color=TEAL)
    arrow(ax, (0.25, 0.53), (0.25, 0.43), color=BLUE)
    arrow(ax, (0.75, 0.53), (0.75, 0.43), color=TEAL)
    arrow(ax, (0.25, 0.27), (0.40, 0.16), color=GOLD)
    arrow(ax, (0.75, 0.27), (0.60, 0.16), color=GOLD)
    save(
        fig,
        "figure_1_2_rq_objective_mapping",
        "Mapping of the research questions, objectives and evaluation evidence.",
        "Chapter 1 - Introduction",
        "Developed by the researcher from the approved research proposal.",
    )


def fig_03_literature_evolution():
    fig, ax = new_canvas((7.2, 3.8))
    heading(ax, "Evolution of intelligent continuous testing")
    xvals = [0.10, 0.36, 0.62, 0.88]
    labels = [
        ("Traditional automation", "Rigid scripts\nFull-suite execution\nManual diagnosis"),
        ("ML-assisted testing", "Predictive selection\nFlaky-test prediction\nSpecialized models"),
        ("LLM-assisted testing", "Test generation\nNatural-language reasoning\nSelf-healing support"),
        ("Agentic LLM-CTF", "End-to-end orchestration\nAdaptive decisions\nGoverned autonomy"),
    ]
    colors = [(PALE_ORANGE, ORANGE), (PALE_GOLD, GOLD), (PALE_BLUE, BLUE), (PALE_TEAL, TEAL)]
    ax.plot([0.10, 0.88], [0.48, 0.48], color=GRID, linewidth=5, solid_capstyle="round")
    for i, (x, (title, body), (fc, ec)) in enumerate(zip(xvals, labels, colors)):
        ax.add_patch(Circle((x, 0.48), 0.035, facecolor=ec, edgecolor=WHITE, linewidth=2, zorder=3))
        box(ax, x - 0.105, 0.58, 0.21, 0.22, f"{title}\n\n{body}", fc=fc, ec=ec, fontsize=8.9, weight="normal")
        ax.text(x, 0.36, f"Stage {i + 1}", ha="center", va="top", fontsize=9, color=MID)
    ax.text(0.50, 0.17, "Increasing scope: execution support  ->  artifact intelligence  ->  lifecycle orchestration", ha="center", color=NAVY, fontweight="bold", fontsize=10)
    note(ax, "Conceptual synthesis of the literature reviewed in the proposal.")
    save(
        fig,
        "figure_2_1_evolution_intelligent_testing",
        "Evolution from traditional test automation to agentic LLM-driven continuous testing.",
        "Chapter 2 - Literature Review",
        "Synthesized by the researcher from the literature reviewed in the proposal.",
    )


def fig_04_research_gap():
    fig, ax = new_canvas((7.2, 4.8))
    heading(ax, "Research gap and proposed contribution")
    ax.text(0.18, 0.85, "EXISTING CAPABILITIES", ha="center", color=BLUE, fontweight="bold")
    existing = ["LLM test generation", "Predictive test selection", "Flaky-test detection", "Self-healing automation", "General DevOps agents"]
    for i, t in enumerate(existing):
        box(ax, 0.04, 0.70 - i * 0.12, 0.28, 0.075, t, fc=PALE_BLUE, ec=BLUE, fontsize=9.3)
    box(ax, 0.38, 0.31, 0.25, 0.40, "RESEARCH GAP\n\nCapabilities remain\nisolated\n\nLimited autonomous\nvalidation\n\nPrototype-scale evidence\n\nApproval bottleneck", fc=PALE_ORANGE, ec=ORANGE, fontsize=8.1, weight="bold")
    box(ax, 0.69, 0.31, 0.28, 0.40, "PROPOSED CONTRIBUTION\n\nIntegrated modular\nLLM-CTF\n\nQuality-aware test\nlifecycle\n\nTraditional-vs-agentic\nevaluation\n\nExplainable oversight", fc=PALE_TEAL, ec=TEAL, fontsize=8.1, weight="bold")
    for y, target_y in zip([0.73, 0.61, 0.49, 0.37, 0.25], [0.65, 0.58, 0.51, 0.44, 0.37]):
        arrow(ax, (0.325, y), (0.375, target_y), color=ORANGE, lw=1.0)
    arrow(ax, (0.635, 0.51), (0.695, 0.51), color=TEAL, lw=2.0)
    note(ax, "The contribution integrates previously separate testing capabilities into a governed workflow.")
    save(
        fig,
        "figure_2_2_research_gap_contribution",
        "Research gap addressed by the proposed LLM-CTF framework.",
        "Chapter 2 - Literature Review",
        "Developed by the researcher from the research-gap analysis in the proposal.",
    )


def fig_05_dsr_cycle():
    fig, ax = new_canvas((6.6, 5.4))
    heading(ax, "Artifact-centric Design Science Research cycle")
    centers = [(0.50, 0.78), (0.79, 0.50), (0.50, 0.22), (0.21, 0.50)]
    items = [
        ("1. Design and development", "Build modular\nLLM-CTF agents", PALE_BLUE, BLUE),
        ("2. Demonstration", "Integrate with\ncase-study CI/CD", PALE_GOLD, GOLD),
        ("3. Evaluation", "Compare metrics and\nanalyze results", PALE_TEAL, TEAL),
        ("4. Communication", "Report findings and\nactionable guidance", PALE_ORANGE, ORANGE),
    ]
    for (cx, cy), (title, body, fc, ec) in zip(centers, items):
        box(ax, cx - 0.17, cy - 0.075, 0.34, 0.15, f"{title}\n{body}", fc=fc, ec=ec, fontsize=8.4, weight="bold")
    for i in range(4):
        a = centers[i]
        b = centers[(i + 1) % 4]
        arrow(ax, a, b, color=NAVY, lw=1.8, connection="arc3,rad=0.20")
    ax.add_patch(Circle((0.50, 0.50), 0.11, facecolor=NAVY, edgecolor=NAVY))
    ax.text(0.50, 0.50, "LLM-CTF\nARTIFACT", ha="center", va="center", color=WHITE, fontweight="bold", fontsize=11)
    note(ax, "Evaluation findings feed back into redesign and refinement.")
    save(
        fig,
        "figure_3_1_dsr_methodology_cycle",
        "Design Science Research cycle used to develop and evaluate the LLM-CTF artifact.",
        "Chapter 3 - Methodology",
        "Adapted by the researcher from the DSR approach specified in the proposal.",
    )


def fig_06_architecture():
    fig, ax = new_canvas((7.2, 5.3))
    heading(ax, "Implemented LLM-CTF prototype architecture", "Generation, predictive selection and guarded autonomous repair are integrated in CI")
    box(ax, 0.04, 0.72, 0.18, 0.11, "Developer\ncommit / pull request", fc=PALE_GOLD, ec=GOLD, fontsize=9.5)
    box(ax, 0.29, 0.72, 0.20, 0.11, "GitHub Actions\nCI/CD orchestrator", fc=PALE_BLUE, ec=BLUE, fontsize=9.5, weight="bold")
    box(ax, 0.57, 0.72, 0.18, 0.11, "FastAPI\nsystem under test", fc=PALE_TEAL, ec=TEAL, fontsize=9.5)
    box(ax, 0.81, 0.72, 0.15, 0.11, "OpenAPI +\nsample responses", fc=WHITE, ec=TEAL, fontsize=8.9)
    box(ax, 0.11, 0.42, 0.24, 0.15, "TestGenAgent\nGenerate and validate\npytest tests", fc=PALE_BLUE, ec=BLUE, fontsize=8.7, weight="bold")
    box(ax, 0.40, 0.42, 0.20, 0.15, "OpenRouter\nGemini LLM", fc=PALE_GOLD, ec=GOLD, fontsize=9.5, weight="bold")
    box(ax, 0.65, 0.42, 0.24, 0.15, "TestSelectAgent\nRank, execute and\nheal failed tests", fc=PALE_TEAL, ec=TEAL, fontsize=8.7, weight="bold")
    box(ax, 0.08, 0.16, 0.22, 0.12, "Generated +\nhandwritten tests", fc=WHITE, ec=NAVY, fontsize=9.4)
    box(ax, 0.39, 0.16, 0.22, 0.12, "Pytest + AST policy\nand rollback gate", fc=WHITE, ec=NAVY, fontsize=8.9)
    box(ax, 0.70, 0.16, 0.22, 0.12, "CSV, timing +\nrepair audit artifacts", fc=WHITE, ec=NAVY, fontsize=8.9)
    arrow(ax, (0.22, 0.775), (0.285, 0.775), color=GOLD)
    arrow(ax, (0.49, 0.775), (0.565, 0.775), color=BLUE)
    arrow(ax, (0.75, 0.775), (0.805, 0.775), color=TEAL)
    arrow(ax, (0.86, 0.71), (0.30, 0.58), color=TEAL, connection="arc3,rad=-0.10")
    arrow(ax, (0.39, 0.71), (0.24, 0.58), color=BLUE)
    arrow(ax, (0.39, 0.71), (0.77, 0.58), color=BLUE)
    arrow(ax, (0.35, 0.50), (0.395, 0.50), color=GOLD)
    arrow(ax, (0.60, 0.50), (0.645, 0.50), color=GOLD)
    arrow(ax, (0.23, 0.41), (0.19, 0.29), color=BLUE)
    arrow(ax, (0.19, 0.16), (0.385, 0.22), color=NAVY)
    arrow(ax, (0.77, 0.41), (0.61, 0.26), color=TEAL)
    arrow(ax, (0.615, 0.22), (0.695, 0.22), color=NAVY)
    arrow(ax, (0.77, 0.42), (0.50, 0.29), color=ORANGE, connection="arc3,rad=0.16")
    note(ax, "LLM credentials are supplied only on trusted push/manual runs; pull requests use the deterministic fallback and a secret-free final gate.")
    save(
        fig,
        "figure_3_2_llm_ctf_architecture",
        "Architecture of the implemented LLM-CTF prototype.",
        "Chapter 3 - Methodology / System Design",
        "Developed by the researcher from main.py, the agent modules and the GitHub Actions workflow.",
    )


def fig_07_cicd_workflow():
    fig, ax = new_canvas((7.2, 4.9))
    heading(ax, "CI/CD integration workflow of the prototype")
    stages = [
        "Checkout\nsource",
        "Install\ndependencies",
        "Start and\nhealth-check API",
        "Generate tests +\nvalidate guardrails",
        "Capture full-suite\nbaseline evidence",
        "Select, heal +\nrepeat validation",
        "Secret-free final\nfull-suite gate",
        "Compare, audit +\nupload artifacts",
    ]
    colors = [(PALE_GOLD, GOLD), (PALE_BLUE, BLUE), (PALE_TEAL, TEAL), (PALE_BLUE, BLUE), (LIGHT, NAVY), (PALE_TEAL, TEAL), (PALE_ORANGE, ORANGE), (PALE_GOLD, GOLD)]
    xs = [0.03, 0.27, 0.51, 0.75]
    ys = [0.66, 0.31]
    positions = [(xs[i], ys[0]) for i in range(4)] + [(xs[i], ys[1]) for i in reversed(range(4))]
    for i, ((x, y), text, (fc, ec)) in enumerate(zip(positions, stages, colors)):
        box(ax, x, y, 0.20, 0.14, f"{i + 1}\n{text}", fc=fc, ec=ec, fontsize=9.2, weight="bold")
    for i in range(len(positions) - 1):
        x1, y1 = positions[i]
        x2, y2 = positions[i + 1]
        if i == 3:
            arrow(ax, (x1 + 0.10, y1 - 0.01), (x2 + 0.10, y2 + 0.15), color=NAVY, connection="arc3,rad=-0.25")
        else:
            arrow(ax, (x1 + (0.21 if x2 > x1 else -0.01), y1 + 0.07), (x2 + (0 if x2 > x1 else 0.20), y2 + 0.07), color=NAVY)
    box(ax, 0.12, 0.06, 0.76, 0.14, "Evidence artifacts\nBefore/final CSV + timing | Repair JSON + accepted patch + backups\nHEAD/worktree audit | Comparison report | Final-suite result", fc=WHITE, ec=MID, fontsize=7.5)
    save(
        fig,
        "figure_3_3_cicd_integration_workflow",
        "CI/CD integration workflow used by the implemented prototype.",
        "Chapter 3 - Methodology / Implementation",
        "Developed by the researcher from .github/workflows/ci-cd.yaml.",
    )


def fig_08_testgen_flow():
    fig, ax = new_canvas((7.2, 4.6))
    heading(ax, "TestGenAgent workflow")
    steps = [
        ("1", "Fetch OpenAPI specification", PALE_TEAL, TEAL),
        ("2", "Enumerate API operations", PALE_BLUE, BLUE),
        ("3", "Build sample request and response", PALE_GOLD, GOLD),
        ("4", "Construct constrained pytest prompt", PALE_BLUE, BLUE),
        ("5", "Generate code via LLM", PALE_GOLD, GOLD),
        ("6", "Strip fences and validate Python AST", PALE_TEAL, TEAL),
        ("7", "Write test module and execute pytest", LIGHT, NAVY),
        ("8", "Export coverage and CSV results", PALE_ORANGE, ORANGE),
    ]
    positions = [(0.04 + i * 0.24, 0.62) for i in range(4)] + [(0.76 - i * 0.24, 0.25) for i in range(4)]
    for (x, y), (num, txt, fc, ec) in zip(positions, steps):
        box(ax, x, y, 0.20, 0.16, f"{num}\n{wrap(txt, 19)}", fc=fc, ec=ec, fontsize=8.1, weight="bold")
    for i in range(7):
        x1, y1 = positions[i]
        x2, y2 = positions[i + 1]
        if i == 3:
            arrow(ax, (x1 + 0.10, y1 - 0.01), (x2 + 0.10, y2 + 0.17), color=NAVY, connection="arc3,rad=-0.25")
        else:
            arrow(ax, (x1 + (0.21 if x2 > x1 else -0.01), y1 + 0.08), (x2 + (0 if x2 > x1 else 0.20), y2 + 0.08), color=NAVY)
    note(ax, "If no API key is configured, the module executes the committed generated-test fallback.")
    save(
        fig,
        "figure_3_4_testgen_agent_workflow",
        "Operational workflow of the TestGenAgent.",
        "Chapter 3 - Methodology / Implementation",
        "Developed by the researcher from tests_generated/generator.py.",
    )


def fig_09_testselect_flow():
    fig, ax = new_canvas((7.2, 4.7))
    heading(ax, "Predictive test-selection workflow", "Known baseline failures are prioritized; failed selected nodes enter the guarded repair flow")
    box(ax, 0.03, 0.66, 0.19, 0.13, "Code diff", fc=PALE_GOLD, ec=GOLD, fontsize=10, weight="bold")
    box(ax, 0.27, 0.66, 0.19, 0.13, "Parse changed files\nand lines", fc=PALE_BLUE, ec=BLUE, fontsize=9.5)
    box(ax, 0.51, 0.66, 0.19, 0.13, "Collect available\npytest test IDs", fc=PALE_BLUE, ec=BLUE, fontsize=9.5)
    box(ax, 0.75, 0.66, 0.21, 0.13, "LLM relevance\nranking\nHIGH / MEDIUM / LOW", fc=PALE_GOLD, ec=GOLD, fontsize=8.1, weight="bold")
    for x1, x2 in [(0.22, 0.27), (0.46, 0.51), (0.70, 0.75)]:
        arrow(ax, (x1, 0.725), (x2, 0.725), color=NAVY)
    diamond = Polygon([(0.50, 0.49), (0.61, 0.39), (0.50, 0.29), (0.39, 0.39)], closed=True, facecolor=PALE_ORANGE, edgecolor=ORANGE, linewidth=1.5)
    ax.add_patch(diamond)
    ax.text(0.50, 0.39, "Runnable tests\nselected?", ha="center", va="center", fontsize=9.5, fontweight="bold")
    arrow(ax, (0.84, 0.65), (0.58, 0.47), color=NAVY)
    box(ax, 0.04, 0.12, 0.31, 0.12, "No: use deterministic\nimpacted-test fallback", fc=PALE_ORANGE, ec=ORANGE, fontsize=8.4)
    box(ax, 0.65, 0.12, 0.31, 0.12, "Yes: execute HIGH\n(+ MEDIUM when enabled)", fc=PALE_TEAL, ec=TEAL, fontsize=8.4)
    box(ax, 0.33, 0.035, 0.34, 0.13, "Batch execution\nFailure -> guarded healing\nFinal CSV + timing", fc=WHITE, ec=NAVY, fontsize=7.9, weight="bold")
    arrow(ax, (0.44, 0.34), (0.31, 0.24), color=ORANGE)
    arrow(ax, (0.56, 0.34), (0.69, 0.24), color=TEAL)
    arrow(ax, (0.35, 0.16), (0.405, 0.13), color=NAVY)
    arrow(ax, (0.65, 0.16), (0.595, 0.13), color=NAVY)
    ax.text(0.34, 0.31, "NO", color=ORANGE, fontweight="bold", fontsize=8.5)
    ax.text(0.66, 0.31, "YES", color=TEAL, fontweight="bold", fontsize=8.5)
    save(
        fig,
        "figure_3_5_testselect_agent_workflow",
        "Predictive test-selection workflow of the TestSelectAgent.",
        "Chapter 3 - Methodology / Implementation",
        "Developed by the researcher from tests_selecter/selecter.py.",
    )


def fig_10_self_healing():
    fig, ax = new_canvas((7.2, 5.5))
    heading(ax, "Guarded autonomous self-healing transaction", "A repair is retained only after policy checks, two node reruns and final selected-batch validation")
    flow = [
        (0.02, "1  Failed node\nNormalize ID +\nextract function", PALE_ORANGE, ORANGE),
        (0.26, "2  LLM decision\nOne function or\nNO_FIX", PALE_GOLD, GOLD),
        (0.50, "3  AST policy gate\nSignature, asserts,\ncalls + safety", PALE_BLUE, BLUE),
        (0.74, "4  Atomic apply\nSnapshot +\nbackup", PALE_TEAL, TEAL),
    ]
    for x, txt, fc, ec in flow:
        box(ax, x, 0.68, 0.20, 0.15, txt, fc=fc, ec=ec, fontsize=7.9, weight="bold")
    for x1, x2 in [(0.22, 0.26), (0.46, 0.50), (0.70, 0.74)]:
        arrow(ax, (x1, 0.755), (x2, 0.755), color=NAVY)

    box(ax, 0.12, 0.43, 0.31, 0.13, "5  Base function rerun x2\nAll parameter cases must pass", fc=PALE_BLUE, ec=BLUE, fontsize=8.5, weight="bold")
    box(ax, 0.57, 0.43, 0.31, 0.13, "6  Final selected-batch run\nNo regression may remain", fc=PALE_TEAL, ec=TEAL, fontsize=8.5, weight="bold")
    arrow(ax, (0.84, 0.67), (0.38, 0.57), color=BLUE, connection="arc3,rad=-0.10")
    arrow(ax, (0.43, 0.495), (0.57, 0.495), color=NAVY)

    box(ax, 0.02, 0.16, 0.28, 0.14, "REJECT / FAIL\nNo change or verified\nbyte-exact rollback", fc=PALE_ORANGE, ec=ORANGE, fontsize=8.2, weight="bold")
    box(ax, 0.36, 0.16, 0.28, 0.14, "ALL CHECKS PASS\nKeep the repaired\ntest function", fc=PALE_TEAL, ec=TEAL, fontsize=8.2, weight="bold")
    box(ax, 0.70, 0.16, 0.28, 0.14, "AUDIT EVIDENCE\nJSON + patch + backup\nhashes + timing", fc=WHITE, ec=MID, fontsize=8.2, weight="bold")
    arrow(ax, (0.20, 0.68), (0.16, 0.31), color=ORANGE, connection="arc3,rad=0.10")
    arrow(ax, (0.55, 0.68), (0.24, 0.31), color=ORANGE, connection="arc3,rad=0.14")
    arrow(ax, (0.70, 0.43), (0.55, 0.31), color=TEAL)
    arrow(ax, (0.79, 0.43), (0.27, 0.31), color=ORANGE, connection="arc3,rad=-0.18")
    arrow(ax, (0.30, 0.23), (0.695, 0.23), color=MID)
    arrow(ax, (0.64, 0.23), (0.695, 0.23), color=MID)
    note(ax, "Limits: one candidate per function; maximum three functions per run; no autonomous commit/push; safety-test file is protected.")
    save(
        fig,
        "figure_3_6_self_healing_decision_flow",
        "Guarded autonomous self-healing transaction for failed selected tests.",
        "Chapter 3 - Methodology / Implementation",
        "Developed by the researcher from tests_selecter/selecter.py and tests_selecter/self_healing.py.",
        "The implementation combines constrained LLM output with deterministic structural policy checks, repeated execution, transaction-wide rollback and persistent audit evidence.",
    )


def fig_11_experiment_design():
    fig, ax = new_canvas((7.2, 4.7))
    heading(ax, "Traditional-versus-agentic experimental design", "Repair-engine guardrail tests are validated separately from the 78-test application inventory")
    box(ax, 0.34, 0.78, 0.32, 0.11, "Same code revision and test inventory", fc=PALE_GOLD, ec=GOLD, fontsize=10, weight="bold")
    box(ax, 0.05, 0.48, 0.36, 0.18, "CONTROL\nTraditional strategy\nExecute all application tests", fc=PALE_BLUE, ec=BLUE, fontsize=10, weight="bold")
    box(ax, 0.59, 0.48, 0.36, 0.18, "TREATMENT\nAgentic strategy\nSelect 16; heal failures; validate", fc=PALE_TEAL, ec=TEAL, fontsize=9.6, weight="bold")
    arrow(ax, (0.43, 0.78), (0.25, 0.67), color=BLUE)
    arrow(ax, (0.57, 0.78), (0.75, 0.67), color=TEAL)
    box(ax, 0.08, 0.23, 0.30, 0.11, "Full-suite CSV", fc=WHITE, ec=BLUE, fontsize=9.5)
    box(ax, 0.62, 0.23, 0.30, 0.11, "Before/final CSV\n+ repair audit", fc=WHITE, ec=TEAL, fontsize=8.7)
    arrow(ax, (0.23, 0.48), (0.23, 0.35), color=BLUE)
    arrow(ax, (0.77, 0.48), (0.77, 0.35), color=TEAL)
    box(ax, 0.20, 0.05, 0.60, 0.11, "Comparison metrics\nTests run | Non-passed | Strategy wall time | Skipped percentage", fc=PALE_ORANGE, ec=ORANGE, fontsize=8.0, weight="bold")
    arrow(ax, (0.23, 0.23), (0.42, 0.16), color=NAVY)
    arrow(ax, (0.77, 0.23), (0.58, 0.16), color=NAVY)
    save(
        fig,
        "figure_3_7_experimental_design",
        "Experimental design for comparing traditional and agentic test execution strategies.",
        "Chapter 3 - Methodology / Evaluation Design",
        "Developed by the researcher from tests_selecter/comparison_report.py and the CI workflow.",
    )


def fig_12_metrics_framework():
    fig, ax = new_canvas((7.2, 4.8))
    heading(ax, "Evaluation metrics framework")
    box(ax, 0.37, 0.73, 0.26, 0.13, "LLM-CTF\nEvaluation", fc=NAVY, ec=NAVY, color=WHITE, fontsize=11, weight="bold")
    groups = [
        (0.03, 0.43, "Effectiveness", ["Test coverage", "Defect detection", "Relevant tests selected"], PALE_BLUE, BLUE),
        (0.27, 0.16, "Efficiency", ["Execution time", "Tests executed / skipped", "Generation effort"], PALE_GOLD, GOLD),
        (0.52, 0.16, "Reliability", ["Pass stability", "Repair success rate", "Verified rollback rate"], PALE_TEAL, TEAL),
        (0.76, 0.43, "Governance", ["Policy rejection rate", "Audit completeness", "Protected-file integrity"], PALE_ORANGE, ORANGE),
    ]
    for x, y, title, metrics, fc, ec in groups:
        box(ax, x, y, 0.21, 0.25, f"{title.upper()}\n\n" + "\n".join(metrics), fc=fc, ec=ec, fontsize=8.8, weight="bold")
        arrow(ax, (0.50, 0.72), (x + 0.105, y + 0.26), color=ec, connection="arc3,rad=0.08")
    note(ax, "CSV/timing files measure execution; self_healing_report.json records repair, rejection, rollback and audit outcomes.")
    save(
        fig,
        "figure_3_8_evaluation_metrics_framework",
        "Metrics framework for evaluating LLM-CTF effectiveness, efficiency, reliability and governance.",
        "Chapter 3 - Methodology / Evaluation Design",
        "Developed by the researcher from RO2 and the proposal's stated evaluation criteria.",
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_results():
    full = read_csv(ROOT / "test-results.csv")
    selected = read_csv(ROOT / "reports" / "test_results.csv")
    generated = read_csv(ROOT / "reports" / "generated_test_results.csv")
    comparison = read_csv(ROOT / "reports" / "comparison_report.csv")
    return full, selected, generated, comparison


def result_axes(title: str, subtitle: str | None = None, figsize=(7.2, 4.5)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.suptitle(title, x=0.08, y=0.98, ha="left", fontsize=14, fontweight="bold", color=NAVY)
    if subtitle:
        ax.set_title(subtitle, loc="left", fontsize=9.5, color=MID, pad=13)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def fig_13_test_counts():
    full, selected, _, _ = load_results()
    values = [len(full), len(selected)]
    fig, ax = result_axes("Tests executed by strategy", "Observed values from the current measured comparison run")
    bars = ax.bar(["Traditional full suite", "Agentic selected subset"], values, color=[BLUE, TEAL], width=0.55)
    ax.set_ylabel("Number of tests executed")
    ax.set_ylim(0, max(values) * 1.25)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, str(v), ha="center", fontweight="bold", color=INK)
    skipped_pct = (values[0] - values[1]) / values[0] * 100
    ax.text(0.5, max(values) * 1.12, f"{skipped_pct:.1f}% fewer tests executed", ha="center", color=ORANGE, fontweight="bold", fontsize=11)
    save(
        fig,
        "figure_4_1_tests_executed_comparison",
        "Number of tests executed by the traditional and agentic strategies.",
        "Chapter 4 - Results and Findings",
        "Calculated from test-results.csv and reports/test_results.csv.",
        f"The predictive selector executed {values[1]} of {values[0]} application tests, reducing the executed test count by {skipped_pct:.1f}% in this run.",
    )


def fig_14_execution_time():
    _, selected, _, comparison = load_results()
    row = next(r for r in comparison if r["metric"] == "Total execution time (s)")
    values = [float(row["traditional"]), float(row["agentic"])]
    fig, ax = result_axes("Measured test-strategy wall time", "Full application batch versus selector + decision + selected batch; excludes the final CI safety gate")
    bars = ax.bar(["Traditional full suite", "Agentic selected subset"], values, color=[BLUE, TEAL], width=0.55)
    ax.set_ylabel("Total execution time (seconds)")
    ax.set_ylim(0, max(values) * 1.25)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.45, f"{v:.3f} s", ha="center", fontweight="bold", color=INK)
    reduction_pct = (values[0] - values[1]) / values[0] * 100
    ax.text(0.5, max(values) * 1.12, f"Selected-workflow time was {reduction_pct:.1f}% lower", ha="center", color=TEAL, fontweight="bold", fontsize=11)
    save(
        fig,
        "figure_4_2_execution_time_comparison",
        "Measured wall time of the traditional full-batch and agentic selected-test strategies.",
        "Chapter 4 - Results and Findings",
        "Calculated from reports/comparison_report.csv.",
        f"The agentic selected-test workflow took {values[1]:.3f} seconds versus {values[0]:.3f} seconds for the full application batch, a {reduction_pct:.1f}% reduction while retaining {len(selected)} impacted tests. This excludes the separate final CI safety gate; no repair was triggered because all selected tests passed.",
    )


def fig_15_selection_outcome():
    full, selected, _, _ = load_results()
    chosen = len(selected)
    skipped = len(full) - chosen
    fig, ax = plt.subplots(figsize=(6.2, 4.8))
    wedges, _ = ax.pie(
        [chosen, skipped],
        startangle=90,
        counterclock=False,
        colors=[TEAL, GRID],
        wedgeprops={"width": 0.34, "edgecolor": WHITE, "linewidth": 2},
    )
    ax.text(0, 0.06, f"{chosen}/{len(full)}", ha="center", va="center", fontsize=22, fontweight="bold", color=NAVY)
    ax.text(0, -0.14, "tests selected", ha="center", va="center", fontsize=10, color=MID)
    ax.set_title("Predictive selection outcome", loc="left", fontsize=14, fontweight="bold", color=NAVY, pad=10)
    ax.legend(wedges, [f"Selected ({chosen})", f"Skipped ({skipped})"], loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=2, frameon=False)
    save(
        fig,
        "figure_4_3_predictive_selection_outcome",
        "Distribution of selected and skipped tests in the predictive-selection run.",
        "Chapter 4 - Results and Findings",
        "Calculated from test-results.csv and reports/test_results.csv.",
    )


def short_test_name(test_id: str) -> str:
    name = test_id.split("::")[-1]
    if "[" in name:
        base, parameter = name.split("[", 1)
        parameter = parameter.rstrip("]").split("-", 1)[-1]
        name = f"{base} ({parameter})"
    return name.replace("test_", "").replace("_", " ")


def fig_16_paired_runtimes():
    full, selected, _, _ = load_results()
    full_map = {r["id"]: float(r["duration"]) for r in full}
    selected_rows = [r for r in selected if r["id"] in full_map]
    names = [wrap(short_test_name(r["id"]), 24) for r in selected_rows]
    traditional = [full_map[r["id"]] for r in selected_rows]
    agentic = [float(r["duration"]) for r in selected_rows]
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(7.2, 8.5))
    h = 0.35
    ax.barh(y - h / 2, traditional, height=h, color=BLUE, label="Traditional full-suite batch")
    ax.barh(y + h / 2, agentic, height=h, color=TEAL, label="Agentic selected batch")
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlabel("Duration (seconds)")
    paired_traditional = sum(traditional)
    paired_agentic = sum(agentic)
    ax.set_title(
        f"Per-test call durations for the same {len(selected_rows)} selected tests\n"
        f"Duration sum: traditional {paired_traditional:.3f}s | agentic {paired_agentic:.3f}s",
        loc="left",
        fontsize=13,
        fontweight="bold",
        color=NAVY,
        pad=12,
    )
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend(frameon=False, loc="lower right")
    save(
        fig,
        "figure_4_4_paired_test_durations",
        "Paired duration comparison for tests executed under both strategies.",
        "Chapter 4 - Results and Findings",
        "Calculated by matching test IDs in test-results.csv and reports/test_results.csv.",
        f"The same {len(selected_rows)} tests are paired by node ID. The selected-workflow speed difference primarily comes from executing fewer tests and batching them in one pytest process.",
    )


def generated_category(test_id: str) -> str:
    name = test_id.lower()
    if any(k in name for k in ["health", "reset", "seed", "error_injection", "metrics"]):
        return "Observability / test hooks"
    if "users" in name or "user_id" in name:
        return "Users"
    if "posts" in name or "post_id" in name:
        return "Posts"
    if "slow_data" in name or "large_payload" in name:
        return "Performance"
    return "Other"


def fig_17_generated_coverage():
    _, _, generated, _ = load_results()
    generated_passed = sum(row.get("status") == "passed" for row in generated)
    categories: dict[str, int] = {}
    for row in generated:
        key = generated_category(row["id"])
        categories[key] = categories.get(key, 0) + 1
    order = ["Observability / test hooks", "Users", "Posts", "Performance", "Other"]
    order = [k for k in order if categories.get(k)]
    values = [categories[k] for k in order]
    fig, ax = result_axes("LLM-generated tests by API capability", f"{generated_passed} of {len(generated)} generated tests passed in the observed run")
    bars = ax.bar(order, values, color=[NAVY, BLUE, TEAL, GOLD, MID][: len(order)], width=0.60)
    ax.set_ylabel("Generated test count")
    ax.set_ylim(0, max(values) + 1.5)
    ax.tick_params(axis="x", rotation=12)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.12, str(v), ha="center", fontweight="bold")
    save(
        fig,
        "figure_4_5_generated_tests_by_capability",
        "Distribution of LLM-generated tests across API capability groups.",
        "Chapter 4 - Results and Findings",
        "Calculated from reports/generated_test_results.csv; categories were assigned from test identifiers.",
        f"The generator result contains {len(generated)} tests, of which {generated_passed} passed, covering users, posts, performance, observability and test-hook capabilities.",
    )


def fig_18_suite_composition():
    full, _, _, _ = load_results()
    generated_count = sum(1 for r in full if r["id"].startswith("tests_generated/"))
    handwritten_count = len(full) - generated_count
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    ax.barh(["Application-test inventory"], [handwritten_count], color=BLUE, label=f"Handwritten tests ({handwritten_count})")
    ax.barh(["Application-test inventory"], [generated_count], left=[handwritten_count], color=TEAL, label=f"LLM-generated tests ({generated_count})")
    ax.text(handwritten_count / 2, 0, str(handwritten_count), ha="center", va="center", color=WHITE, fontweight="bold", fontsize=12)
    ax.text(handwritten_count + generated_count / 2, 0, str(generated_count), ha="center", va="center", color=WHITE, fontweight="bold", fontsize=12)
    ax.set_xlim(0, len(full))
    ax.set_xlabel("Number of tests")
    ax.set_title("Composition of the application-test inventory", loc="left", fontsize=14, fontweight="bold", color=NAVY, pad=12)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.30), ncol=2)
    save(
        fig,
        "figure_4_6_complete_suite_composition",
        "Composition of the application-test inventory by test origin.",
        "Chapter 4 - Results and Findings",
        "Calculated from test-results.csv using the test module path.",
        f"The application experiment contained {handwritten_count} handwritten tests and {generated_count} generated tests; repair-engine guardrail tests are reported separately.",
    )


def write_manifest():
    final_suite_count = len(read_csv(ROOT / "reports" / "final_suite_after_heal.csv"))
    selected_rows = read_csv(ROOT / "reports" / "test_results.csv")
    selected_failed = sum(
        row.get("status", "").lower() != "passed" for row in selected_rows
    )
    repair_evidence = (
        "The observed selected batch had no failures, so repair correctness is "
        "supported by deterministic guardrail tests rather than a live repair "
        "outcome in this run."
        if selected_failed == 0
        else "The repair audit artifacts must be consulted for the observed failed selected tests."
    )
    lines = [
        "# Thesis visualization pack",
        "",
        "This pack contains thesis-ready figures for **Enhancing Continuous Testing in DevOps and CI/CD Pipelines Using Large Language Models**. Each figure is supplied as:",
        "",
        "- `SVG` - editable vector artwork (preferred for revision)",
        "- `PDF` - vector format for final typesetting",
        "- `PNG` - 300-DPI raster format for Microsoft Word",
        "",
        "The suggested numbering is provisional. Renumber each figure to match its final chapter position. Per the supplied thesis guideline, center every figure, use a 10-point sentence-case caption, include the chapter in the figure number, and refer to every figure by number in the body text.",
        "",
        "## Figures and captions",
        "",
    ]
    for index, item in enumerate(CAPTIONS, 1):
        lines.extend(
            [
                f"### {index}. {item['stem']}",
                "",
                f"- **Suggested placement:** {item['chapter']}",
                f"- **Caption:** {item['caption']}",
                f"- **Source line:** Source: {item['source']}",
            ]
        )
        if item["interpretation"]:
            lines.append(f"- **Suggested interpretation:** {item['interpretation']}")
        lines.extend(
            [
                f"- **Files:** [{item['stem']}.png](output/{item['stem']}.png) | [{item['stem']}.svg](output/{item['stem']}.svg) | [{item['stem']}.pdf](output/{item['stem']}.pdf)",
                "",
            ]
        )
    lines.extend(
        [
            "## Evidence boundaries",
            "",
            f"Figures 1.1-3.8 are conceptual, methodological, or implementation diagrams. Figures 4.1-4.6 are computed from the current workspace CSV files and describe one prototype run; they must not be generalized as final research findings without repeated experiments, uncertainty estimates, and controlled replications. Figure 4.2 compares the 78-test application batch with the selector/decision/16-test batch only; the separate {final_suite_count}-test post-healing CI safety gate is excluded from that efficiency comparison. {repair_evidence}",
            "",
            "## Regeneration",
            "",
            "Run `python visualizations/generate_visualizations.py` from the repository root after replacing the CSV reports with updated experimental results.",
            "",
        ]
    )
    (Path(__file__).resolve().parent / "README.md").write_text("\n".join(lines), encoding="utf-8")


def create_contact_sheet():
    from PIL import Image, ImageDraw

    pngs = sorted(OUT.glob("figure_*.png"))
    thumb_w, thumb_h = 520, 360
    margin, label_h, columns = 24, 42, 3
    rows = math.ceil(len(pngs) / columns)
    sheet = Image.new("RGB", (columns * (thumb_w + margin) + margin, rows * (thumb_h + label_h + margin) + margin), "white")
    draw = ImageDraw.Draw(sheet)
    for i, path in enumerate(pngs):
        img = Image.open(path).convert("RGB")
        img.thumbnail((thumb_w, thumb_h))
        col, row = i % columns, i // columns
        x = margin + col * (thumb_w + margin)
        y = margin + row * (thumb_h + label_h + margin)
        ox = x + (thumb_w - img.width) // 2
        oy = y + (thumb_h - img.height) // 2
        sheet.paste(img, (ox, oy))
        draw.text((x, y + thumb_h + 8), path.stem, fill=INK)
    sheet.save(Path(__file__).resolve().parent / "contact_sheet.png", dpi=(150, 150))


def main():
    generators = [
        fig_01_research_model,
        fig_02_rq_objective_mapping,
        fig_03_literature_evolution,
        fig_04_research_gap,
        fig_05_dsr_cycle,
        fig_06_architecture,
        fig_07_cicd_workflow,
        fig_08_testgen_flow,
        fig_09_testselect_flow,
        fig_10_self_healing,
        fig_11_experiment_design,
        fig_12_metrics_framework,
        fig_13_test_counts,
        fig_14_execution_time,
        fig_15_selection_outcome,
        fig_16_paired_runtimes,
        fig_17_generated_coverage,
        fig_18_suite_composition,
    ]
    for generator in generators:
        generator()
    write_manifest()
    create_contact_sheet()
    print(f"Generated {len(CAPTIONS)} thesis figures in {OUT}")


if __name__ == "__main__":
    main()
