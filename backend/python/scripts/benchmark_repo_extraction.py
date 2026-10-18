import argparse
from collections import Counter
import json
from pathlib import Path
import time
import zipfile

from app.ingestion.categories import seed_settings
from app.ingestion.code_parser import python_structure
from app.ingestion.config import processing_config
from app.ingestion.local_models import relex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--sample-file', required=True)
    parser.add_argument('--sample-characters', type=int, default=1800)
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    started = time.monotonic()
    counts = Counter()
    relations = Counter()
    errors = []
    with zipfile.ZipFile(arguments.archive) as archive:
        sources = [item for item in archive.infolist() if item.filename.endswith('.py')]
        for source in sources:
            text = archive.read(source).decode('utf-8-sig')
            counts['pythonFiles'] += 1
            counts['lines'] += len(text.splitlines())
            try:
                structure = python_structure(text, source.filename)
                counts['entities'] += len(structure['entities'])
                counts['relationships'] += len(structure['relationships'])
                relations.update(edge['predicate'] for edge in structure['relationships'])
            except (SyntaxError, ValueError) as error:
                errors.append({'file': source.filename, 'error': str(error)})
        matching = [item for item in sources if item.filename.endswith(arguments.sample_file)]
        if len(matching) != 1:
            raise ValueError('Sample filename must identify one Python source in the archive')
        sample = archive.read(matching[0]).decode('utf-8-sig')[:arguments.sample_characters]
    result = {'fixtureOnly': True, 'hostedModelCalls': 0, 'archive': str(arguments.archive), 'syntax': {**dict(counts), 'seconds': time.monotonic() - started, 'relations': dict(relations), 'errors': errors}, 'sampleFile': matching[0].filename, 'sampleCharacters': len(sample)}
    print(json.dumps(result['syntax']), flush=True)
    config = processing_config()
    profile = seed_settings(['code_repository'])
    started = time.monotonic()
    first = relex(sample, profile, config)
    result['loadAndFirstInferenceSeconds'] = time.monotonic() - started
    started = time.monotonic()
    result['rawCodeOutput'] = relex(sample, profile, config)
    result['warmInferenceSeconds'] = time.monotonic() - started
    result['rawCodeOutput']['scoreMeaning'] = 'Uncalibrated scores; predictions are not verified against Python semantics'
    result['model'] = first['model']
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'model': result['model'], 'loadAndFirstInferenceSeconds': result['loadAndFirstInferenceSeconds'], 'warmInferenceSeconds': result['warmInferenceSeconds'], 'entityCount': len(result['rawCodeOutput']['entities']), 'relationships': [{'subject': edge['head']['text'], 'predicate': edge['relation'], 'object': edge['tail']['text'], 'score': edge['score']} for edge in result['rawCodeOutput']['relationships']]}), flush=True)


if __name__ == '__main__':
    main()
