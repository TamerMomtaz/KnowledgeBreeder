"""The vector reader recovers pipes, tees, boxes, symbols and tags from a synthetic CAD-like page."""

from __future__ import annotations

import pytest

reportlab = pytest.importorskip("reportlab")
pytest.importorskip("pypdfium2")

from reportlab.pdfgen import canvas  # noqa: E402

from knowledgebreeder.readers import get  # noqa: E402


@pytest.fixture()
def mini_pid(tmp_path):
    """Two tanks joined by a pipe with a gate valve (bowtie) and a tee branch
    up to a transmitter bubble; a dashed signal from the bubble to a box."""
    path = tmp_path / "mini.pdf"
    c = canvas.Canvas(str(path), pagesize=(800, 500))
    c.rect(20, 20, 760, 460)                        # page frame
    c.rect(80, 150, 100, 140)                       # TK-101
    c.rect(600, 150, 100, 140)                      # TK-102
    c.line(180, 220, 330, 220)                      # pipe, up to the valve
    p = c.beginPath()                               # gate valve bowtie 330..350
    p.moveTo(330, 212); p.lineTo(350, 228); p.lineTo(350, 212); p.lineTo(330, 228); p.close()
    c.drawPath(p)
    c.line(350, 220, 600, 220)                      # pipe, valve to TK-102
    c.line(450, 220, 450, 330)                      # tee branch up
    c.circle(450, 342, 12)                          # FIT bubble
    c.setDash(4, 3)
    c.line(462, 342, 560, 342)                      # dashed signal
    c.setDash()
    c.setFont("Helvetica", 9)
    c.drawString(100, 300, "TK-101")
    c.drawString(620, 300, "TK-102")
    c.drawString(328, 232, "HV-201")
    c.drawString(470, 360, "FIT-0502")
    c.drawString(300, 450, "GENERAL NOTES APPLY")
    c.save()
    return str(path)


def test_skeleton(mini_pid):
    res = get("vector_geometry").read(mini_pid, 1).to_dict()
    st = res["stats"]
    assert st["boxes"] == 2, st                      # two tanks, frame excluded
    assert st["tees"] == 1, st                       # the branch to the transmitter
    assert st["signal_runs"] == 1, st                # the dashed line
    pipes = [r for r in res["runs"] if r["kind"] == "pipe_candidate"]
    # left pipe (tank to valve) and right network (valve to tank, with the tee)
    assert len(pipes) == 2
    right = max(pipes, key=lambda r: len(r["segments"]))
    assert len(right["tees"]) == 1
    assert "B1" in right["touches"]                  # reaches TK-102
    left = min(pipes, key=lambda r: len(r["segments"]))
    assert "B0" in left["touches"]
    # both pipes stop at the valve symbol, which is how the model learns the valve is in-line
    valve = [s["id"] for s in res["symbols"]
             if any(s["id"] in t for t in left["end_touches"].values())]
    assert valve and any(valve[0] in t for t in right["end_touches"].values())


def test_tags(mini_pid):
    res = get("vector_geometry").read(mini_pid, 1).to_dict()
    near = {t["text"]: t["near"] for t in res["tags"]}
    assert set(near) == {"TK-101", "TK-102", "HV-201", "FIT-0502"}  # prose is not a tag
    assert near["TK-101"] == "B0" and near["TK-102"] == "B1"
    assert near["HV-201"].startswith("S") and near["FIT-0502"].startswith("S")


def test_normalized_coordinates(mini_pid):
    res = get("vector_geometry").read(mini_pid, 1).to_dict()
    for n in res["nodes"]:
        assert 0 <= n["xy"][0] <= 1 and 0 <= n["xy"][1] <= 1
    # origin top-left: the pipe at y=220pt on a 500pt page sits at v = 0.56
    vs = {round(s["a"][1], 2) for s in res["segments"] if s["style"] == "solid" and s["a"][1] == s["b"][1]}
    assert 0.56 in vs
