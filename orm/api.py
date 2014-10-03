import copy
import json
import logging
import requests

from gevent import monkey

from . import status, exceptions, relations as rel
from .caches import CacheDict
from .resources import Resource, Collection
from .utils import ZeroDefaultDict


#logging.basicConfig()
log = logging.getLogger(__name__)

if False: # TODO optionally disable gevent
    monkey.patch_all(thread=False, select=False)


class Api(Resource):
    """
    Represents a REST API encapsulating some assumptions about its behaviour
    
     - application/json is the default content-type
     - tokens is the default authentication mechanism
    
    However this tries to be a generic implementation, support for other methods
    and types can be achieved by means of subclassing and method overiding
    """
    CONTENT_TYPE = 'application/json'
    SERIALIZE_IGNORES = Resource.SERIALIZE_IGNORES + [
        'username', 'password', 'token', 'stats', 'cache_enabled', 'cache',
    ]
    DEFAULT_HEADERS = {
        'accept': CONTENT_TYPE,
        'content-type': CONTENT_TYPE,
    }
    ResponseStatusError = exceptions.ResponseStatusError
    
    def __init__(self, url, username='', password='', cache=False):
        super(Api, self).__init__(self, url=url)
        self.username = username
        self.password = password
        self.cache_enabled = cache
        self.cache = CacheDict()
        self.stats = ZeroDefaultDict()
    
    def serialize_response(self, content):
        """ hook for other content-type response serialization """
        if self.CONTENT_TYPE == 'application/json':
            return json.loads(content or '{}')
        else:
            msg = "serialization for '%s' response not implemented"
            raise NotImplementedError(msg % self.CONTENT_TYPE)
    
    def serialize_request(self, content):
        """ hook for other content-type request serialization """
        if self.CONTENT_TYPE == 'application/json':
            class ResourceJSONEncoder(json.JSONEncoder):
                def default(self, obj):
                    try:
                        return super(ResourceJSONEncoder, self).default(obj)
                    except TypeError:
                        return obj.serialize()
            return json.dumps(content, cls=ResourceJSONEncoder)
        else:
            msg = "serialization for '%s' request not implemented"
            raise NotImplementedError(msg % self.CONTENT_TYPE)
    
    def request(self, method, *args, **kwargs):
        """ request engine, everything goes through this path """
        headers = kwargs.get('headers', dict(self.DEFAULT_HEADERS))
        headers.update(kwargs.pop('extra_headers', {}))
        kwargs['headers'] = headers
        method_name = method.__name__.lower()
        log.info('REQUEST: %s%s' % (method_name.upper(), str(args)))
        self.stats[method_name] += 1
        if method in [requests.get, requests.head] and self.cache_enabled:
            try:
                response = self.cache.get(args, kwargs)
            except KeyError:
                response = method(*args, **kwargs)
                self.cache.put((args, kwargs), response)
                log_msg = ' '.join((str(response.status_code), response.reason))
            else:
                # TODO inconsistency between invalidated entries and cache.hits counter
                if not response.is_valid and 'If-None-Match' not in kwargs['headers']:
                    # Invalidated cache entries perform as conditional requests
                    kwargs['headers']['If-None-Match'] = response.headers['etag']
                    cond_response = method(*args, **kwargs)
                    status_code = cond_response.status_code
                    log_msg = ' '.join((str(status_code), cond_response.reason))
                    if status_code != status.HTTP_304_NOT_MODIFIED:
                        response = cond_response
                        self.cache.put((args, kwargs), response)
                else:
                    log_msg = ' '.join((str(response.status_code), response.reason))
        else:
            response = method(*args, **kwargs)
            if self.cache_enabled and response.status_code/100 == 2:
                self.cache.invalidate(url=args[0])
            log_msg = ' '.join((str(response.status_code), response.reason))
        if 'If-None-Match' in kwargs['headers']:
            self.stats['conditional'] += 1
        log.debug('KWARGS: %s' % str(kwargs))
        log.debug('RESPONSE: %s' % log_msg)
        return response
    
    def get(self, url, **kwargs):
        """ low level get method """
        return self.request(requests.get, url, **kwargs)
    
    def post(self, url, *args, **kwargs):
        """ low level post method """
        if args:
            # File-like posting
            if hasattr(args[0], 'fileno'):
                kwargs['files'] = {'file': args[0]}
                kwargs['extra_headers'] = {
                    'content-type': None
                }
                args = args[1:]
            else:
                args = (self.serialize_request(args[0]),) + args[1:]
        return self.request(requests.post, url, *args, **kwargs)
    
    def put(self, url, *args, **kwargs):
        """ low level put method """
        if args:
            args = (self.serialize_request(args[0]),) + args[1:]
        return self.request(requests.put, url, *args, **kwargs)
    
    def patch(self, url, *args, **kwargs):
        """ low level patch method """
        if args:
            args = (self.serialize_request(args[0]),) + args[1:]
        return self.request(requests.patch, url, *args, **kwargs)
    
    def delete(self, url, **kwargs):
        """ low level delete method """
        return self.request(requests.delete, url, **kwargs)
    
    def head(self, url, **kwargs):
        """ low level delete method """
        return self.request(requests.head, url, **kwargs)
    
    def create(self, url, data=None, extra_headers={}, headers=None, **kwargs):
        """ high level api method for creating objects """
        if data is None:
            obj = Resource(self, **kwargs)
            data = obj.serialize()
        kwargs = {
            'extra_headers': extra_headers
        }
        if headers is not None:
            kwargs['headers'] = headers
        response = self.post(url, data, **kwargs)
        self.validate_response(response, status.HTTP_201_CREATED)
        return Resource.from_response(self, response)
    
    def retrieve_base(self):
        """ retrieve self """
        response = self.get(self.url)
        expected = [status.HTTP_200_OK, status.HTTP_304_NOT_MODIFIED]
        self.validate_response(response, expected)
        # Make sure self.url is the base and not something else
        for relation,content in response.links.iteritems():
            if rel.get_name(relation) == 'base':
                if content['url'] != response.url:
                    self.url = content['url']
                    response = self.get(self.url)
        # avoid further queries on __getattr__
        self._has_retrieved = True
        base = Resource.from_response(self, response)
        self.merge(base)
        self.process_links()
    
    def retrieve(self, *args, **kwargs):
        """ high level api method for retrieving objects """
        if not args:
            self.retrieve_base()
        elif len(args) != 1:
            raise ValueError('Too many positional arguments')
        else:
            url = args[0]
            # Hack to retrieve objects by id
            pk = kwargs.pop('id', None)
            if pk is not None:
                url += '%d/' % pk
            # Server side-filtering
            filtering = []
            for key in kwargs.keys():
                if key not in ['extra_headers']:
                    value = kwargs.pop(key)
                    filtering.append('%s=%s' % (key,value))
            if filtering:
                url += '?' + '&'.join(filtering)
            response = self.get(url, **kwargs)
            expected = [status.HTTP_200_OK, status.HTTP_304_NOT_MODIFIED]
            self.validate_response(response, expected)
            content = self.serialize_response(response.content)
            url = response.url.split('?')[0]
            if isinstance(content, list):
                resources = [Resource(self, **obj) for obj in content]
                return Collection(resources, api=self, url=url)
            return Resource(self, _headers=response.headers, **content)
    
    def update(self, url, data, **kwargs):
        """ high level api method for updating objects """
        response = self.put(url, data, **kwargs)
        self.validate_response(response, status.HTTP_200_OK)
        content = self.serialize_response(response.content)
        return Resource(self, **content)
        
    def partial_update(self, url, data, **kwargs):
        """ high level api method for partially updating objects """
        response = self.patch(url, data, **kwargs)
        self.validate_response(response, status.HTTP_200_OK)
        content = self.serialize_response(response.content)
        return Resource(self, **content)
    
    def destroy(self, url, **kwargs):
        """ high level api method for deleting objects """
        response = self.delete(url, **kwargs)
        self.validate_response(response, status.HTTP_204_NO_CONTENT)
    
    def validate_response(self, response, codes):
        """ validate response status code """
        if not hasattr(codes, '__iter__'):
            codes = [codes]
        if response.status_code not in codes:
            try:
                content = self.serialize_response(response.content)
            except ValueError:
                # Internal server error with a bunch of html most probably
                content = {'detail': response.content[:200] + '[...]'}
            context = {
                'method': response.request.method,
                'url': response.request.url,
                'code': response.status_code,
                'reason': response.reason,
                'expected': str(codes)[1:-1],
                'detail': content.get('detail', content)
            }
            msg = "%(method)s(%(url)s): %(code)d %(reason)s (!= %(expected)s) %(detail)s"
            raise self.ResponseStatusError(msg % context)
    
    def login(self, username=None, password=None):
        """ further requests will use authentication """
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password
        self.logout()
        credentials = self.get_auth_token(username=self.username, password=self.password)
        token = 'Token %s' % credentials.token
        self.DEFAULT_HEADERS['authorization'] = token
        self._has_retrieved = False
    
    def logout(self):
        """ further requests will not use authentication """
        self.DEFAULT_HEADERS.pop('authorization', None)
    
    def close(self):
        """ close connection """
        requests.post(self.url, headers={'Connection':'close'})
    
    @classmethod
    def enable_logging(cls, *verbosity):
        verbosity = verbosity[0] if verbosity else 'INFO'
        verbosity = getattr(logging, verbosity)
        cls.logger = logging.getLogger(__name__)
        cls.logger.setLevel(verbosity)
    
    @classmethod
    def disable_logging(cls):
        cls.logger.setLevel(logging.ERROR)
