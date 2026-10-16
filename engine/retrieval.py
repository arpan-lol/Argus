import math
import re
from collections import Counter
from .models import Candidate


def tokens(text):
    return re.findall(r"\w+", text.casefold())


class BM25Retriever:
    def __init__(self, store):
        self.store = store

    def search(self, query, limit=10):
        rows = self.store.records("evidence")
        counts = [Counter(tokens(row["quote"])) for row in rows]
        lengths = [sum(c.values()) for c in counts]
        avg = sum(lengths) / len(lengths) if lengths else 1
        terms = set(tokens(query))
        frequency = {t: sum(t in c for c in counts) for t in terms}
        scored = []
        for row, count, length in zip(rows, counts, lengths):
            score = 0.0
            for term in terms:
                tf = count[term]
                if tf:
                    idf = math.log(1 + (len(rows) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                    score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
            if score > 0:
                scored.append((row["id"], score))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return [Candidate(eid, score, "bm25", i + 1) for i, (eid, score) in enumerate(scored[:limit])]
