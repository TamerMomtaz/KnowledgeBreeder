# Candidates to try next

Checked 2026-11-11. Each needs a score before it is believed.

| Candidate | What it would add | Evidence so far | Source |
|---|---|---|---|
| Hand the vector skeleton to the seed's extraction step | The model labels exact geometry instead of tracing lines | Reader works on a synthetic page; not yet scored on a real drawing | `knowledgebreeder/readers/vector_geometry.py` |
| Two-stage reading with a design-rules document | Edge accuracy 50% to 81% and 38% to 74% on two drawings | One paper, two drawings, Gemini 3 Pro, no code | [LAPSE:2026.0420](https://psecommunity.org/LAPSE:2026.0420) |
| PID2Graph as a public score | A number that outsiders can reproduce | Loader written from the dataset description; not yet run on the download | [Zenodo 14803338](https://zenodo.org/records/14803338) |
| RF-DETR P&ID symbol detector for scans | Offline symbol hints where there is no vector data | 99.96% mAP@50 on its own test set only | [HF model](https://huggingface.co/dimtri009/rfdetr-pid-detector) |
| pyDEXPI export | A real DEXPI model instead of an informative mapping | v2.1.0, 2026-11-01; AGPL-3.0, so keep it optional | [PyPI](https://pypi.org/project/pyDEXPI/) |
| PFD against P&ID check | Every PFD stream with no P&ID path is a likely missed edge | Idea borrowed from layout-versus-schematic checks in chip design | none yet |
