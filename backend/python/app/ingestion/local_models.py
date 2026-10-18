import threading
import gc
import logging


_models = {}
_locks = {}
_registry_lock = threading.Lock()
_torch_configured = False
_compute_lock = threading.Lock()
logger = logging.getLogger('argus.local_models')


def available_memory_bytes():
    try:
        import psutil
        return psutil.virtual_memory().available
    except ImportError:
        return 1024 * 1024 * 1024


def memory_failure(error):
    return isinstance(error, MemoryError) or any(value in str(error).lower() for value in ('not enough memory', 'out of memory', 'defaultcpuallocator', 'cannot allocate memory'))


def relation_inference(model, texts, rows, labels, relations, config, batch_size):
    effective = max(1, min(batch_size, available_memory_bytes() // (768 * 1024 * 1024)))
    rows = sorted(rows, key=lambda row: row[2] - row[1])
    results = []
    for start in range(0, len(rows), effective):
        group = rows[start:start + effective]
        failed = False
        try:
            with _compute_lock:
                entities, links = model.inference(texts=[texts[owner][left:right] for owner, left, right in group], labels=labels, relations=relations, threshold=config['relexEntityThreshold'], adjacency_threshold=config['relexAdjacencyThreshold'], relation_threshold=config['relexRelationThreshold'], flat_ner=True, multi_label=False, return_relations=True, batch_size=len(group))
            results.extend(zip(group, entities, links, strict=True))
        except (RuntimeError, MemoryError) as error:
            if not memory_failure(error):
                raise
            failed = True
            logger.warning('Reducing local relation work after allocation failure: items=%s characters=%s error=%s', len(group), sum(right - left for _, left, right in group), str(error)[:180])
        if failed:
            gc.collect()
            if len(group) > 1:
                middle = len(group) // 2
                results.extend(relation_inference(model, texts, group[:middle], labels, relations, config, 1))
                results.extend(relation_inference(model, texts, group[middle:], labels, relations, config, 1))
            else:
                owner, left, right = group[0]
                words = list(model.data_processor.words_splitter(texts[owner][left:right]))
                overlap = min(config['glinerOverlapWords'], max(1, len(words) // 8))
                if len(words) <= 16:
                    raise RuntimeError('Local relation extraction exceeded available memory even at its smallest safe window')
                half = len(words) // 2
                a_end = left + words[min(len(words) - 1, half + overlap)][2]
                b_start = left + words[max(1, half - overlap)][1]
                pieces = [(owner, left, a_end), (owner, b_start, right)]
                results.extend(relation_inference(model, texts, pieces, labels, relations, config, 1))
    return results


def configure_runtime(config):
    global _torch_configured
    with _registry_lock:
        if not _torch_configured:
            import torch
            threads = config.get('localModelThreads', 8)
            if not 1 <= threads <= 64:
                raise ValueError('Local model thread count must be between 1 and 64')
            torch.set_num_threads(threads)
            _torch_configured = True


def model_lock(name):
    with _registry_lock:
        return _locks.setdefault(name, threading.Lock())


def load_model(name, config):
    configure_runtime(config)
    from gliner import GLiNER
    try:
        return GLiNER.from_pretrained(name, local_files_only=True)
    except OSError:
        return GLiNER.from_pretrained(name)


def relex(text, profile, config):
    return relex_many([text], profile, config)[0]


def relex_many(texts, profile, config):
    from .batching import service
    from .config import fingerprint
    key = fingerprint([profile['entityTypes'], profile['relationshipTypes'], profile.get('entityDescriptions'), {name: config.get(name) for name in ('relexModel', 'glinerOverlapWords', 'relexEntityThreshold', 'relexAdjacencyThreshold', 'relexRelationThreshold', 'relexBatchSize', 'localModelThreads')}])
    return service('relex').submit(key, texts, lambda values: relex_direct(values, profile, config))


def relex_direct(texts, profile, config):
    name = config["relexModel"]
    with model_lock(name):
        if name not in _models:
            _models[name] = load_model(name, config)
        model = _models[name]
        cap = int(model.config.max_len)
        overlap = config["glinerOverlapWords"]
        if cap <= overlap or overlap < 0:
            raise ValueError("Local model overlap exceeds its supported window")
        batch_size = config.get('relexBatchSize', 4)
        if not 1 <= batch_size <= 16:
            raise ValueError('Local relation batch size must be between 1 and 16')
        entity_labels = {value.replace("_", " "): profile.get("entityDescriptions", {}).get(value, value.replace("_", " ")) for value in profile["entityTypes"]}
        entity_names = {value.replace("_", " "): value for value in profile["entityTypes"]}
        relation_names = {value.replace("_", " "): value for value in profile["relationshipTypes"]}
        outputs = [{'entities': {}, 'relationships': {}, 'windows': [], 'model': name} for text in texts]
        windows = []
        for owner, text in enumerate(texts):
            words = list(model.data_processor.words_splitter(text))
            position = 0
            while position < len(words):
                end = min(position + cap, len(words))
                left = words[position][1] if position else 0
                right = words[end - 1][2] if end < len(words) else len(text)
                windows.append((owner, left, right))
                outputs[owner]['windows'].append({'start': left, 'end': right})
                if end == len(words):
                    break
                position = end - overlap
        if not windows:
            return [{**output, 'entities': [], 'relationships': []} for output in outputs]
        predictions = relation_inference(model, texts, windows, entity_labels, list(relation_names), config, batch_size)
        for output in outputs:
            output['windows'] = []
        for (owner, left, right), items, links in predictions:
            outputs[owner]['windows'].append({'start': left, 'end': right})
            entities, relations = outputs[owner]['entities'], outputs[owner]['relationships']
            for item in items:
                value = {**item, "start": left + item["start"], "end": left + item["end"], "label": entity_names[item["label"]]}
                key = (value["start"], value["end"], value["label"])
                if key not in entities or value["score"] > entities[key]["score"]:
                    entities[key] = value
            for edge in links:
                value = {**edge, "relation": relation_names[edge["relation"]], "head": {**edge["head"], "start": left + edge["head"]["start"], "end": left + edge["head"]["end"]}, "tail": {**edge["tail"], "start": left + edge["tail"]["start"], "end": left + edge["tail"]["end"]}}
                key = (value["head"]["start"], value["head"]["end"], value["relation"], value["tail"]["start"], value["tail"]["end"])
                if key not in relations or value["score"] > relations[key]["score"]:
                    relations[key] = value
        expected = set(windows)
        for owner, output in enumerate(outputs):
            output['memoryWindowSplit'] = any((owner, window['start'], window['end']) not in expected for window in output['windows'])
        return [{**output, 'entities': list(output['entities'].values()), 'relationships': list(output['relationships'].values())} for output in outputs]


def ner_many(texts, types, config, stop_check=lambda: None):
    from .batching import service
    from .config import fingerprint
    key = fingerprint([types, {name: config.get(name) for name in ('glinerModel', 'glinerOverlapWords', 'glinerThreshold', 'glinerWindowing', 'localModelThreads')}])
    return service('ner').submit(key, texts, lambda values: ner_direct(values, types, config), stop_check=stop_check)


def ner_direct(texts, types, config):
    name = config['glinerModel']
    with model_lock(name):
        if name not in _models:
            _models[name] = load_model(name, config)
        model = _models[name]
        cap, overlap = int(model.config.max_len), int(config['glinerOverlapWords'])
        if not 0 <= overlap < cap:
            raise ValueError('GLiNER overlap must be smaller than its word cap')
        outputs = []
        windows = []
        for owner, text in enumerate(texts):
            words = list(model.data_processor.words_splitter(text))
            output = {'mentions': {}, 'coverage': {'status': 'complete', 'strategy': config['glinerWindowing'], 'modelWordCap': cap, 'overlapWords': overlap, 'wordCount': len(words), 'windows': [], 'offsetUnit': 'unicode_code_point'}}
            outputs.append(output)
            position = 0
            while position < len(words):
                end = min(position + cap, len(words))
                left = words[position][1] if position else 0
                right = words[end - 1][2] if end < len(words) else len(text)
                windows.append((owner, left, right))
                output['coverage']['windows'].append({'wordStart': position, 'wordEndExclusive': end, 'startOffset': left, 'endOffset': right})
                if end == len(words):
                    break
                position = end - overlap
        if windows:
            with _compute_lock:
                predictions = model.inference(texts=[texts[owner][left:right] for owner, left, right in windows], labels=types, threshold=config['glinerThreshold'], batch_size=4)
            for (owner, left, _), found in zip(windows, predictions, strict=True):
                for item in found:
                    adjusted = {**item, 'start': item['start'] + left, 'end': item['end'] + left}
                    key = (adjusted['start'], adjusted['end'], adjusted['label'])
                    prior = outputs[owner]['mentions'].get(key)
                    if prior is None or adjusted['score'] > prior['score']:
                        outputs[owner]['mentions'][key] = adjusted
        return [{**output, 'mentions': sorted(output['mentions'].values(), key=lambda item: (item['start'], item['end']))} for output in outputs]
