"""Layer 3: understanding. Knowledge into a map of thoughts, and back out as answers with their sources.

What you keep goes in: your inbox items, your framed books, and your project cards (all of them one subject). A
thought is one idea with the source and words it came from. Thoughts are joined by needs, causes, is part of and
contradicts (said by a model, held to the source) and by "may help" (found by kb from shared words, at once, the
moment a thought arrives). Two thoughts can marry into a new one, which joins the map only with your yes. The map is
drawn as a city: each subject a district, each thought a building (infrastructure, a resource, a utility) or an
empty lot (a need).
"""

from . import ask, city, read
from .store import (CARDS_SUBJECT, HINT, JOINS, KINDS, MARRIED_SUBJECT, ROLES, Map, approve, candidates, decline,
                    gather, gaps, marry_by_hand, summary)

__all__ = ["ask", "city", "read", "CARDS_SUBJECT", "HINT", "JOINS", "KINDS", "MARRIED_SUBJECT", "ROLES", "Map",
           "approve", "candidates", "decline", "gather", "gaps", "marry_by_hand", "summary"]
