"""Layer 2: work processes from plain speech.

Each person describes their job in their own words, one file each. kb joins the hand-offs into one process:
steps, pipes (hand-offs), valves (decisions, with their decision tables), instruments (checks) and joins
(all of, any of, one of). It writes the process as a graph.json, so `kb walk`, `kb stats` and `kb whatif` read it.
"""

from .join import Process, join, stops, whatif
from .report import LABELS, question_text, to_graph, to_markdown
from .speech import Person, parse_sentence, read_all, read_file, read_text

__all__ = ["Process", "join", "stops", "whatif", "LABELS", "question_text", "to_graph", "to_markdown", "Person",
           "parse_sentence", "read_all", "read_file", "read_text"]
