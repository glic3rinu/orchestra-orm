import re


LOOKUPS = {
    'default': lambda a,b: a == b,
    'lt': lambda a,b: a < b,
    'lte': lambda a,b: a <= b,
    'gt': lambda a,b: a > b,
    'gte': lambda a,b: a >= b,
    'in': lambda a,b: a in b,
    'exact': lambda a,b: a == b,
    'iexact': lambda a,b: a.lower() == b.lower(),
    'startswith': lambda a,b: a.startswith(b),
    'istartswith': lambda a,b: a.lower().startswith(b.lower()),
    'contains': lambda a,b: b in a,
    'icontains': lambda a,b: b.lower() in a.lower(),
}


def filter_collection(collection, **kwargs):
    if not kwargs:
        return list(collection.resources)
    exclude = kwargs.pop('_exclude', False)
    result = []
    for resource in collection.resources:
        for key, value in kwargs.iteritems():
            include = False
            attrs = key.split('__')
            try:
                lookup = LOOKUPS[attrs[-1]]
            except KeyError:
                lookup = LOOKUPS.get('default')
            else:
                attrs = attrs[:-1]
            current = resource
            for attr in attrs:
                current = getattr(current, attr)
                if isinstance(current, type(collection)):
                    # "joining" with currenr Collection
                    attr = re.findall(r'%s__(.*)$' % attr, key)[0]
                    partial_kwargs = {
                        attr: value,
                        '_exclude': exclude
                    }
                    include = bool(filter_collection(current, **partial_kwargs))
                    break
            if not isinstance(current, type(collection)):
                if not exclude and lookup(current, value):
                    include = True
                elif exclude and not lookup(current, value):
                    include = True
            if not include:
                break
        if include:
            result.append(resource)
    return result


def retrieve_related(resources, *args, **kwargs):
    soft = kwargs.get('soft', False)
    def fetchable(r):
        return getattr(r, 'uri', None) and not (soft and r._has_retrieved)
    pool = {}
    MAX_RECURSION = 10
    args = list(args)
    for i in range(0, MAX_RECURSION):
        if not args:
            return
        related = {}
        # Collect related objects that need to be retrieved
        for resource in resources:
            for attr in args:
                try:
                    field = attr.split('__')[i]
                except IndexError:
                    args.remove(attr)
                else:
                    current = getattr(resource, field)
                    if not hasattr(current, '__iter__'):
                        if fetchable(current):
                            related[current.uri] = current
                    else:
                        for nested in current:
                            if fetchable(nested):
                                related[nested.uri] = nested
        # Retrieve missing related objects
        to_fetch = set(related.keys()) - set(pool.keys())
        for url in to_fetch:
            related[url].retrieve(async=True)
            pool[url] = related[url]
        next = []
        # Update related objects with retrieved description
        for resource in resources:
            for attr in args:
                field = attr.split('__')[i]
                current = getattr(resource, field)
                if not hasattr(current, '__iter__'):
                    if fetchable(current):
                        pool[current.uri].wait_async()
                        current.merge(pool[current.uri])
                    next.append(current)
                else:
                    for nested in current:
                        if fetchable(current):
                            pool[nested.uri].wait_async()
                            nested.merge(pool[nested.uri])
                    next += current
        resources = next
