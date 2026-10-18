def contextual_input(chunk, text):
    headings = chunk.get('headingContext', [])
    if not headings:
        return text, 0
    label = ' / '.join(str(value) for value in headings)[-256:]
    prefix = 'Source section: ' + label + '\nSource passage:\n'
    return prefix + text, len(prefix)


def remove_context(result, prefix_length):
    if not prefix_length:
        return result

    def adjusted(item):
        return {**item, 'start': item['start'] - prefix_length, 'end': item['end'] - prefix_length}

    entities = [adjusted(item) for item in result['entities'] if item['start'] >= prefix_length]
    positions = {(item['start'], item['end']) for item in entities}
    links = []
    for relation in result['relationships']:
        if relation['head']['start'] < prefix_length or relation['tail']['start'] < prefix_length:
            continue
        head, tail = adjusted(relation['head']), adjusted(relation['tail'])
        if (head['start'], head['end']) in positions and (tail['start'], tail['end']) in positions:
            links.append({**relation, 'head': head, 'tail': tail})
    return {**result, 'entities': entities, 'relationships': links, 'contextPrefixCharacters': prefix_length}
