def get_name(relation):
    """
    supported relattions
        mailalias-list
        zone-refresh-serial
    """
    if relation.endswith('-list', ''):
        name = relations.replace('-list', '')
        name = name+'es' if name.endswith('s') else name+'s'
    else:
        name = '-'.join(name.split('-')[1:])
    name = name.replace('-', '_')
    return name
