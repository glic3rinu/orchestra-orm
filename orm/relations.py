def get_name(relation):
    """
    supported relattions
        mailalias-list
        zone-refresh-serial
    """
    if relation.endswith('-list'):
        name = relation.replace('-list', '')
        name = name+'es' if name.endswith('s') else name+'s'
    elif relation.endswith('-detail'):
        name = relation.replace('-detail', '')
    else:
        name = '-'.join(relation.split('-')[1:])
    name = name.replace('-', '_')
    return name
