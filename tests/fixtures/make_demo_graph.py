"""Writes tests/fixtures/demo_graph.json: a small plant in the seed's graph.json format.

    BOUNDARY:RAW WATER -> V-001 -> TK-101 -> [seg] -> V-002 -> P-101 -> CV-0502 -> FE-0502 -> TK-102 -> V-003 -> BOUNDARY:TO PROCESS
    TK-101 -> P-102 (standby pump, no valves, joins the same discharge before CV-0502)
    Loop F-0502: FE-0502 -> FIT-0502 -> FIC-0502 -> CV-0502.  LI-101 on TK-101.  TK-102 has no instrument.
"""
import json
from pathlib import Path

N, E = [], []

def node(id, type, kind=None, tag=None, conf=0.9, label=None, **attrs):
    N.append({"id": id, "type": type, "label": label or tag or id, "tag": tag, "kind": kind, "name": None, "status": "existing",
              "dexpi_class": None, "sheets": ["SHEET:D-001"], "confidence": conf, "attributes": attrs,
              "provenance": [{"sheet": "D-001", "page": 1, "bbox": None}]})

def edge(s, t, type, conf=0.9, derived=False, **attrs):
    E.append({"id": f"E{len(E)}", "source": s, "target": t, "type": type, "confidence": conf,
              "derived": derived, "attributes": attrs, "sheet": "SHEET:D-001"})

node("PLANT:DEMO", "Plant"); node("SHEET:D-001", "Sheet", page=1, drawing_number="D-001")
node("BOUNDARY:RAW WATER", "Boundary", direction="source"); node("BOUNDARY:TO PROCESS", "Boundary", direction="sink")
node("TK-101", "Equipment", "tank", "TK-101"); node("TK-102", "Equipment", "tank", "TK-102")
node("P-101", "Equipment", "centrifugal_pump", "P-101"); node("P-102", "Equipment", "centrifugal_pump", "P-102", conf=0.6)
for v, k in (("V-001", "gate_valve"), ("V-002", "gate_valve"), ("V-003", "ball_valve")):
    node(v, "Component", k, v)
node("CV-0502", "Component", "control_valve", "CV-0502", role="final_element", loop_key="F-0502", fail_position="FC")
node("FE-0502", "Instrument", None, "FE-0502", variable="flow", role="primary_element", inline=True, loop_key="F-0502")
node("FIT-0502", "Instrument", None, "FIT-0502", variable="flow", role="transmitter", location="field", loop_key="F-0502")
node("FIC-0502", "Instrument", None, "FIC-0502", variable="flow", role="controller", location="dcs", loop_key="F-0502")
node("LI-101", "Instrument", None, "LI-101", variable="level", role="indicator", location="field")
for s in ("P01.L1.1", "P01.L2.1", "P01.L2.2", "P01.L3.1", "P01.L3.2", "P01.L3.3", "P01.L4.1", "P01.L5.1"):
    node(s, "PipeSegment", line_number=s.split(".")[1])
node("LOOP:F-0502", "ControlLoop", "control", label="F-0502", loop_type="control", variable="flow", sensors=["FE-0502", "FIT-0502"],
     controllers=["FIC-0502"], final_elements=["CV-0502"], description="FIC-0502 controls flow by moving CV-0502")

chain = ["BOUNDARY:RAW WATER", "V-001", "P01.L1.1", "TK-101", "P01.L2.1", "V-002", "P01.L2.2", "P-101", "P01.L3.1",
         "CV-0502", "P01.L3.2", "FE-0502", "P01.L3.3", "TK-102", "P01.L4.1", "V-003", "BOUNDARY:TO PROCESS"]
for a, b in zip(chain, chain[1:]):
    edge(a, b, "FLOWS_TO")
edge("TK-101", "P01.L5.1", "FLOWS_TO", conf=0.6, flow_direction="inferred")
edge("P01.L5.1", "P-102", "FLOWS_TO", conf=0.6, flow_direction="inferred")
edge("P-102", "P01.L3.1", "FLOWS_TO", conf=0.6, flow_direction="inferred")
for a, b in (("BOUNDARY:RAW WATER", "TK-101"), ("TK-101", "P-101"), ("TK-101", "P-102"), ("P-101", "TK-102"),
             ("P-102", "TK-102"), ("TK-102", "BOUNDARY:TO PROCESS")):
    edge(a, b, "FEEDS", derived=True)
edge("FE-0502", "P01.L3.2", "MEASURES"); edge("FIT-0502", "P01.L3.2", "MEASURES"); edge("LI-101", "TK-101", "MEASURES")
edge("FE-0502", "FIT-0502", "SIGNAL_TO", signal_type="electrical", purpose="measurement")
edge("FIT-0502", "FIC-0502", "SIGNAL_TO", signal_type="electrical", purpose="measurement")
edge("FIC-0502", "CV-0502", "SIGNAL_TO", signal_type="pneumatic", purpose="control")
edge("FIC-0502", "CV-0502", "ACTUATES", derived=True)
for m, r in (("FE-0502", "sensor"), ("FIT-0502", "sensor"), ("FIC-0502", "controller"), ("CV-0502", "final_element")):
    edge(m, "LOOP:F-0502", "MEMBER_OF", derived=True, role=r)

out = {"schema_version": "1.0", "generator": "tests/fixtures/make_demo_graph.py", "generated_at": "2026-11-11T00:00:00Z",
       "plant": {"id": "DEMO", "name": "Demo plant", "source_file": None}, "nodes": N, "edges": E, "stats": {}, "issues": []}
Path(__file__).with_name("demo_graph.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(len(N), "nodes", len(E), "edges")
