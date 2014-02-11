import functools

from . import status
from . import relations as rel


class Manager(object):
    """ collection manager, proxies Api methods and also provides custome ones """
    registry = {}
    
    def __init__(self, endpoint, relation, api):
        self.endpoint = endpoint
        self.relation = relation
        self.api = api
    
    def __call__(self, *args, **kwargs):
        """ action resource manager """
        from .resources import Resource
        # TODO move to an Action class, and Register(profiles.NODE)
        if kwargs:
            response = self.api.post(self.endpoint, kwargs)
        else:
            response = self.api.post(self.endpoint, *args)
        valid_codes = [
            status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED
        ]
        self.api.validate_response(response, valid_codes)
        content = self.api.serialize_response(response.content)
        return Resource(self, _headers=response.headers, **content)
    
    def __getattr__(self, name):
        """ custom and proxied manager methods """
        try:
            # lookup for custom methods
            method = self.get_method(name)
            method = functools.partial(method, self)
        except KeyError:
            # lookup for proxied api methods
            method = getattr(self.api, name)
        return functools.partial(method, self.endpoint)
    
    @classmethod
    def register(cls, relation):
        """ register decorator @Manager.register(rel.SERVER_USERS) """
        def registred_method(func, *args, **kwargs):
            cls.registry.setdefault(relation, [])
            cls.registry[relation].append(func)
            return func
        return registred_method
    
    @classmethod
    def unregister(cls, relation, method):
        cls.registry[relation].remove(method)
    
    def get_method(self, name):
        """ get registered methods by method name """
        methods = type(self).registry[self.relation]
        for method in methods:
            if method.__name__ == name:
                return method
        raise KeyError('%s not registered in %s' % (name, self.relation))


@Manager.register(rel.SERVER_USERS)
def create(manager, endpoint, *args, **kwargs):
    """ creates a user with password """
    password = kwargs.pop('password', None)
    user = manager.create(endpoint, **kwargs)
    if password:
        user.change_password(password)
    return user


def create_with_file_factory(fields):
    def create_with_file(manager, endpoint, fields=fields, *args, **kwargs):
        files = []
        for field in fields:
            files.append((field, kwargs.pop(field, None)))
            if files[-1][1]:
                kwargs['%s_uri' % field] = 'http://dummy.uri/dummytemplate.tgz'
                kwargs['%s_sha256' % field] = '76a71abd164ce3b149c84d52a4bd313e74cae75539bd5c10628b784792ba039c'
        obj = manager.create(endpoint, **kwargs)
        for field, value in files:
            if value:
                getattr(obj, 'upload_%s' % field)(value)
        obj.retrieve()
        return obj
    return create_with_file


create_with_file = create_with_file_factory(['image'])
Manager.register(rel.SERVER_TEMPLATES)(create_with_file)
create_with_file = create_with_file_factory(['overlay', 'exp_data'])
Manager.register(rel.SERVER_SLICES)(create_with_file)
Manager.register(rel.SERVER_SLIVERS)(create_with_file)
