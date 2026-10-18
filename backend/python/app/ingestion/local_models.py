import threading


_models = {}
_locks = {}
_registry_lock = threading.Lock()
_torch_configured = False


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
        found, edges = model.inference(texts=[texts[owner][left:right] for owner, left, right in windows], labels=entity_labels, relations=list(relation_names), threshold=config["relexEntityThreshold"], adjacency_threshold=config["relexAdjacencyThreshold"], relation_threshold=config["relexRelationThreshold"], flat_ner=True, multi_label=False, return_relations=True, batch_size=batch_size)
        for (owner, left, right), items, links in zip(windows, found, edges, strict=True):
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
        return [{**output, 'entities': list(output['entities'].values()), 'relationships': list(output['relationships'].values())} for output in outputs]
