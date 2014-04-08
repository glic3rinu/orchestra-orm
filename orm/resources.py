import json
import logging
import re
from copy import copy

import gevent

from . import helpers
from . import relations as rel
from .files import FileHandler
from .managers import Manager
from .utils import DisabledStderr


#logging.basicConfig()
log = logging.getLogger(__name__)

def isurl(value):
    return isinstance(value, basestring) and value.startswith('http')

class Resource(object):
    """ schema-free resource representation (active record) """
    SERIALIZE_IGNORES = ['api', 'manager']
    
    def __repr__(self):
        module, name = type(self).__module__, type(self).__name__
        return "<%s.%s: %s>" % (module, name, self.url or id(self))
    
    def __str__(self):
        return json.dumps(self.serialize(), indent=4)
    
    def __init__(self, *args, **kwargs):
        self._serialize_ignores = list(self.SERIALIZE_IGNORES)
        self.url = None
        self.api = None
        self.manager = None
        if args:
            self.api = args[0]
        self._headers = dict(kwargs.get('_headers', {}))
        if self._headers:
            self.process_links()
        self._has_retrieved = bool(self._headers and 'link' in self._headers)
        # Build nested Resource structure
        for name, value in kwargs.iteritems():
            if not name.startswith('_'):
                if name != 'url' and isurl(value):
                    value = Resource(*args, url=value)
                elif isinstance(value, list):
                    if value and isurl(value[0]):
                        value = [ Resource(*args, url=url) for url in value ]
                    value = RelatedCollection(value, parent=self, related_name=name)
                self.__dict__[name] = value
        self._set_file_handlers()
    
    def __getattr__(self, name):
        """ fetch and cache missing nested resources """
        if not name == 'url' and not name.startswith('_') and self.api and self.url:
            if not self._has_retrieved:
                self.retrieve()
                return getattr(self, name)
        msg = "'%s' object has no attribute '%s'"
        raise AttributeError(msg % (str(type(self)), name))
    
    def __eq__(self, other):
        if not isinstance(other, Resource):
            return False
        if self.url and other.url:
            return self.url == other.url
        if self.manager != other.manager:
            return False
        return self._data == other._data
    
    def _set_file_handlers(self):
        """ add a file handler for related resource files """
        data = self._data
        for name, value in data.iteritems():
            if name.endswith('_url'):
                field_name = name.replace('_url', '')
                sha256_field_name = '%s_sha256' % field_name
                if sha256_field_name in data:
                    setattr(self, field_name, FileHandler(self, field_name))
                    self._serialize_ignores.append(field_name)
    
    @classmethod
    def from_response(cls, api, response):
        """ constructor method accepting a response object """
        content = api.serialize_response(response.content)
        resource = cls(api, _headers=response.headers, **content)
        return resource
    
    @property
    def _data(self):
        """ hide internal methods and attributes """
        data = {}
        for name, value in self.__dict__.iteritems():
            if not name.startswith('_') and name not in self._serialize_ignores:
                if name == 'url' and value is None:
                    continue
                data[name] = value
        return data
    
    def get_links(self):
        """ get link header urls mapped by relation """
        links = {}
        link_header = self._headers.get('link', False)
        if link_header:
            for line in link_header.split(','):
                link = re.findall(r'<(.*)>', line)[0]
                relation = re.findall(r'"(.*)"', line)[0]
                links[relation] = link
        return links
    
    def process_links(self):
        """ get extra managers from link relations """
        links = self.get_links()
        for relation, link in links.iteritems():
            name = rel.get_name(relation)
            if name not in self.__dict__:
                setattr(self, name, Manager(link, relation, self.api))
                self._serialize_ignores.append(name)
    
    def get_name(self):
        """ getting the resource name, suggestions are welcome :) """
        if self.url:
            url = self.url
            if not url.endswith('/'):
                url += '/'
            return url.split('/')[-3].replace('-', '_')[:-1]
        elif self.manager:
            type, name = rel.get_name(self.manager.relation)
            if name.endswith('es'):
                name = name[:-2]
            elif name.endswith('s'):
                name = name[:-1]
            return name
        raise ValueError("don't know the name")
    
    def save(self):
        """ save object on remote and update field values from response """
        if self.url:
            self.validate_binding()
            resource = self.api.update(self.url, self.serialize())
        else:
            self.validate_binding()
            resource = self.manager.create(self.serialize())
        self.merge(resource)
    
    def merge(self, resource):
        """  merge input resource attributes to current resource """
        for key, value in resource._data.iteritems():
            setattr(self, key, value)
        self._set_file_handlers()
        self._headers.update(resource._headers)
        if not self._has_retrieved:
            self._has_retrieved = resource._has_retrieved
    
    def delete(self):
        """ delete remote object """
        self.validate_binding(url=True)
        self.api.destroy(self.url)
    
    def update(self, **kwargs):
        """ partial remote update of the object """
        self.validate_binding(url=True)
        resource = self.api.partial_update(self.url, kwargs)
        self.merge(resource)
    
    def wait_async(self):
        with DisabledStderr():
            self._glet.get()
        if self._glet._exception:
            log.error(glet._exception)
    
    def retrieve(self, conditional=True, async=False):
        """ retrieve remote state of this object """
        def do_retrieve(conditional, async):
            extra_headers = {}
            if conditional and self._has_retrieved and not self.api.cache_enabled:
                etag = self._headers.get('etag', None)
                if etag:
                    etag = etag.replace(';gzip', '')
                    extra_headers = {'If-None-Match': etag}
            resource = self.api.retrieve(self.url, extra_headers=extra_headers)
            if resource:
                self.merge(resource)
                self.process_links()
            self._has_retrieved = True
        
        if async and False: # TODO gevent option
            self._glet = gevent.spawn(do_retrieve, conditional, async)
            self.api.stats['async'] += 1
        else:
            do_retrieve(conditional, async)
    
    def serialize(self, isnested=False):
        """ serialize object for storing in remote server """
        raw_data = self._data
        if isnested and 'url' in raw_data:
            return raw_data['url']
        data = {}
        for key, value in raw_data.iteritems():
            if type(value) in (Resource, RelatedCollection, Collection):
                value = value.serialize(isnested=True)
            data[key] = value
        return data
    
    def bind(self, manager):
        """ bind object to an api endpoint """
        self.api = manager.api
        self.manager = manager
    
    def validate_binding(self, manager=False, url=False):
        """ checks if current object state satisfies bind requirements """
        if not self.api:
            raise TypeError('this resouce is not bound to an Api')
        if not self.url and not self.manager:
            raise TypeError('this resource has no url nor related Api endpoint')
        if manager and not self.manager:
            raise TypeError('this resource has no related Api endpoint')
        if url and not self.url:
            raise TypeError('this resource has no url')


class Collection(object):
    """ represents a uniform collection of resources """
    REPR_OUTPUT_SIZE = 10
    
    def __repr__(self):
        return str(self.resources)
    
    def __str__(self):
        return json.dumps(self.serialize(), indent=4)
    
    def __init__(self, resources, api, url):
        self.resources = resources
        self.api = api
        self.url = url
        self.manager = getattr(self.api, self.get_name())
    
    def __iter__(self):
        return iter(self.resources)
    
    def __getitem__(self, k):
        return self.resources[k]
    
    def __len__(self):
        return len(self.resources)
    
    def __getattr__(self, name):
        """ proxy methods of endpoint manager """
        try:
            return getattr(self.manager, name)
        except AttributeError:
            msg = "'%s' object has no attribute '%s'"
            raise AttributeError(msg % (str(type(self)), name))
    
    def get_name(self):
        url = self.url
        if not url.endswith('/'):
            url += url + '/'
        return url.split('/')[-2]
        
    def serialize(self, isnested=False):
        if self.resources and isinstance(self.resources[0], Resource):
            if isnested:
                return [resource.url for resource in self.resources]
            return [resource.serialize() for resource in self.resources]
        return [resource for resource in self.resources]
    
    def iterator(self, async=True):
        for resource in self.resources:
            resource.retrieve(async=async)
            if not async:
                yield resource
        if async:
            for resource in self.resources:
                resource.wait_async()
                yield resource
    
    def filter(self, **kwargs):
        """ client-side filtering method """
        related = []
        for field in kwargs:
            relations = field.split('__')
            if relations[-1] in helpers.LOOKUPS:
                relations = relations[:-1]
            if len(relations) > 1:
                related.append('__'.join(relations))
        self.retrieve_related(*related, soft=True)
        new = copy(self)
        new.resources = helpers.filter_collection(self, **kwargs)
        return new
    
    def get(self, **kwargs):
        resource = helpers.filter_collection(self, **kwargs)
        if len(resource) > 1:
            raise TypeError('more than one')
        elif len(resource) < 1:
            raise TypeError('not found')
        return resource[0]
    
    def exclude(self, **kwargs):
        kwargs['_exclude'] = True
        new = copy(self)
        new.resources = helpers.filter_collection(self, **kwargs)
        return new
    
    def group_by(self, field):
        self.retrieve_related(field, soft=True)
        groups = {}
        for resource in self.resources:
            current = resource
            for related in field.split('__'):
                current = getattr(current, related)
            groups.setdefault(current, [])
            groups[current].append(resource)
        return groups
    
    def order_by(self, filed, reverse=False):
        self.retrieve_related(field, soft=True)
        def sort_by(resource):
            current = resource
            for related in field.slit('__'):
                current = getattr(current, related)
            return current
        self.resources.sort(key=sort_by)
        if reverse:
            self.resources.reverse()
    
    def bulk(self, method, merge=True, async=True, **kwargs):
        if async and False: # TODO gevent option
            glets = []
            for resource in self.resources:
                args = (resource.url, kwargs) if kwargs else (resource.url,)
                glets.append(gevent.spawn(method(resource.api), *args))
            total = len(glets)
            successes = []
            failures = []
            for glet, resource in zip(glets, self.resources):
                resource.api.stats['async'] += 1
                with DisabledStderr():
                    glet.get()
                if glet._exception:
                    log.error(glet._exception)
                    failures.append(resource)
                else:
                    if merge:
                        resource.merge(glet.value)
                    successes.append(resource)
            return successes, failures
        else:
            for resource in self.resources:
                args = (resource.url, kwargs) if kwargs else (resource.url,)
                method(resource.api, *args)
    
    def destroy(self):
        return self.bulk(lambda n: n.destroy, merge=False)
    
    def update(self, **kwargs):
        """ remote update of all set elements """
        return self.bulk(lambda n: n.partial_update, **kwargs)
    
    def retrieve(self, async=True, **kwargs):
        self.resources = [resource for resource in self.iterator(async=async)]
    
    def retrieve_related(self, *args, **kwargs):
        """ fetched related elements in batch """
        helpers.retrieve_related(self.resources, *args, **kwargs)
    
    def values_list(self, value):
        result = []
        values = value.split('__')
        for resource in self.resources:
            partial_result = None
            current = resource
            for i, attr in enumerate(values):
                if hasattr(current, '__iter__'):
                    partial_result = current.values_list('__'.join(values[i:]))
                    break
                else:
                    current = getattr(current, attr)
            if partial_result is not None:
                result += partial_result
            else:
                result.append(current)
        new = copy(self)
        new.resources = result
        return new
    
    def distinct(self):
        # TODO consistent model for returning new objects or just perform operation
        new = copy(self)
        new.resources = list()
        map(lambda x: not x in new.resources and new.resources.append(x), self.resources)
        return new
    
    def append(self, resource):
        self.resources.append(resource)
    
    def create(self, **kwargs):
        """ create can not be proxied """
        resource = self.manager.create(**kwargs)
        self.resources.append(resource)
        return resource


class RelatedCollection(Collection):
    """ represents a subcollection related to a parent object """
    def __init__(self, resources, parent, related_name):
        self.resources = resources
        self.api = parent.api
        self.related_name = related_name
        self.parent = parent
        try:
            self.manager = getattr(self.api, self.related_name)
        except AttributeError:
            self.manager = None
    
    def get_name(self):
        return self.related_name
    
    def create(self, **kwargs):
        """ appending related object as attributes of new resource """
        kwargs[self.parent.get_name()] = self.parent
        resource = self.manager.create(**kwargs)
        self.resources.append(resource)
        return resource
    
    def retrieve(self):
        """ retrieve related collection taking care of the parent """
        self.parent.retrieve()
        collection = getattr(self.parent, self.related_name)
        super(RelatedCollection, collection).retrieve()
        return collection
    
    def append(self, resource):
        setattr(resource, self.parent.get_name(), self.parent)
        self.resources.append(resource)


class ResourceSet(Collection):
    """
    represents a non-uniform set of resources that can be used for bulk operations
    maximizing concurrent throughput
    """
    def __init__(self, resources):
        self.resources = resources
        self.resources = self.distinct().resources
    
    def __getattr__(self, name):
        msg = "'%s' object has no attribute '%s'"
        raise AttributeError(msg % (str(type(self)), name))
    
    def create(self):
        return AttributeError('non-uniform resources can not be created')
    
    def append(self, resource):
        self.resources.append(resource)
        self.resources = self.distinct().resources
