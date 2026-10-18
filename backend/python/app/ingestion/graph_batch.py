import re
from collections import OrderedDict


class GraphWrites:
    def __init__(self, graph, batch_size=128, vector_batch_size=32):
        self.graph = graph
        self.batch_size = batch_size
        self.vector_batch_size = vector_batch_size
        self.operations = OrderedDict()
        self.query_count = 0
        self.record_count = 0

    def add(self, query, params):
        self.operations.setdefault(query, []).append(params)

    def flush(self):
        for query, rows in self.operations.items():
            size = self.vector_batch_size if "vecf32(" in query else self.batch_size
            statement = "UNWIND $batch AS row " + re.sub(r"\$([A-Za-z_][A-Za-z_0-9]*)", r"row.\1", query)
            for offset in range(0, len(rows), size):
                batch = rows[offset:offset + size]
                self.graph.query(statement, {"batch": batch})
                self.query_count += 1
                self.record_count += len(batch)
        self.operations.clear()


def write_batches(graph, query, key, records, params=None, batch_size=128):
    for offset in range(0, len(records), batch_size):
        graph.query(query, {**(params or {}), key: records[offset:offset + batch_size]})
