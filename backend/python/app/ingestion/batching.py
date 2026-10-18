import threading
from collections import deque
from concurrent.futures import Future, TimeoutError
from dataclasses import dataclass


@dataclass
class BatchItem:
    key: str
    value: object
    operation: object
    weight: int
    future: Future
    request_id: object


class MicroBatcher:
    def __init__(self, name, maximum_items, maximum_weight, workers=1, wait_seconds=0.04):
        self.name = name
        self.maximum_items = maximum_items
        self.maximum_weight = maximum_weight
        self.wait_seconds = wait_seconds
        self.condition = threading.Condition()
        self.pending = deque()
        self.completed_batches = 0
        self.completed_items = 0
        for index in range(workers):
            threading.Thread(target=self.loop, name=f'argus-{name}-{index}', daemon=True).start()

    def submit(self, key, values, operation, weights=None, stop_check=lambda: None):
        weights = weights or [1] * len(values)
        if len(weights) != len(values) or any(weight < 1 or weight > self.maximum_weight for weight in weights):
            raise ValueError('A batch item exceeds the configured processing limit')
        request_id = object()
        items = [BatchItem(key, value, operation, weight, Future(), request_id) for value, weight in zip(values, weights, strict=True)]
        with self.condition:
            self.pending.extend(items)
            self.condition.notify_all()
        try:
            results = []
            for item in items:
                while True:
                    stop_check()
                    try:
                        results.append(item.future.result(timeout=0.25))
                        break
                    except TimeoutError:
                        if item.future.done():
                            raise
            return results
        except BaseException:
            for item in items:
                item.future.cancel()
            raise

    def loop(self):
        while True:
            with self.condition:
                while not self.pending:
                    self.condition.wait()
                self.condition.wait(timeout=self.wait_seconds)
                queued = [item for item in self.pending if not item.future.cancelled()]
                key = queued[0].key if queued else None
                groups = {}
                for item in queued:
                    if item.key == key:
                        groups.setdefault(item.request_id, deque()).append(item)
                batch = []
                weight = 0
                while len(batch) < self.maximum_items:
                    added = False
                    for items in groups.values():
                        if not items or len(batch) >= self.maximum_items:
                            continue
                        item = items[0]
                        if weight + item.weight > self.maximum_weight:
                            continue
                        items.popleft()
                        if item.future.set_running_or_notify_cancel():
                            batch.append(item)
                            weight += item.weight
                        added = True
                    if not added:
                        break
                chosen = {id(item) for item in batch}
                self.pending = deque(item for item in queued if id(item) not in chosen and not item.future.cancelled())
            if not batch:
                continue
            try:
                results = batch[0].operation([item.value for item in batch])
                if len(results) != len(batch):
                    raise ValueError('Batch output count does not match its inputs')
                for item, result in zip(batch, results, strict=True):
                    item.future.set_result(result)
            except Exception as error:
                for item in batch:
                    if not item.future.done():
                        item.future.set_exception(error)
            finally:
                with self.condition:
                    self.completed_batches += 1
                    self.completed_items += len(batch)

    def status(self):
        with self.condition:
            return {'pendingItems': len(self.pending), 'completedBatches': self.completed_batches, 'completedItems': self.completed_items, 'maximumItems': self.maximum_items, 'maximumWeight': self.maximum_weight, 'coalesceMilliseconds': self.wait_seconds * 1000}


_services = {}
_lock = threading.Lock()


def service(name):
    with _lock:
        if name not in _services:
            if name == 'embedding':
                _services[name] = MicroBatcher(name, 256, 32000, workers=2)
            elif name in {'ner', 'relex'}:
                _services[name] = MicroBatcher(name, 32, 65536)
            else:
                raise ValueError('Unknown batch service')
        return _services[name]


def status():
    with _lock:
        return {name: value.status() for name, value in _services.items()}
