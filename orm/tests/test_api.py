import os
import unittest

from orm.api import Api

from .utils import random_ascii


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.api = Api(os.environ['CONFINE_SERVER_API'])
    
    def test_attributes(self):
        self.assertEqual(['uri'], self.api._data.keys())
    
    def test_self_retrieve(self):
        self.api.retrieve()
        self.assertEqual(3, len(self.api._data))
    
    def test_managers(self):
        self.api.nodes
        with self.assertRaises(AttributeError):
            self.api.rata
    
    def test_login(self):
        self.assertRaises(self.api.ResponseStatusError, self.api.login)
        self.api.username = os.environ['CONFINE_USER']
        self.api.password = os.environ['CONFINE_PASSWORD']
        self.api.login()
        auth_header = self.api.DEFAULT_HEADERS['authorization']
        self.assertLess(20, auth_header)
    
    def test_login_providing_credentials(self):
        username = os.environ['CONFINE_USER']
        password = os.environ['CONFINE_PASSWORD']
        self.api.login(username=username, password=password)
        self.assertEqual(self.api.username, username)
        self.assertEqual(self.api.password, password)
        auth_header = self.api.DEFAULT_HEADERS['authorization']
        self.assertLess(20, auth_header)
    
    def test_logout(self):
        self.test_login()
        self.api.logout()
        self.assertNotIn('authorization', self.api.DEFAULT_HEADERS)
    
    def test_retrieve_base(self):
        group = self.api.groups.retrieve()[0]
        name = 'RandomNode-%s' % random_ascii(10)
        self.test_login()
        node = self.api.nodes.create(name=name, group=group)
        controller = Api(node.uri)
        controller.retrieve()
        self.assertEqual(self.api, controller)
        self.assertEqual(self.api._data, controller._data)
    
    def test_caching(self):
        api = Api(os.environ['CONFINE_SERVER_API'], cache=True)
        api.nodes.retrieve()
        self.assertEqual(0, api.cache.hits)
        self.assertEqual(2, api.cache.misses)
        nodes = api.nodes.retrieve()
        self.assertEqual(1, api.cache.hits)
        self.assertEqual(2, api.cache.misses)
        for node in nodes:
            node.retrieve()
        self.assertEqual(len(nodes)+2, api.cache.misses)
        self.assertEqual(1, api.cache.hits)
        for node in nodes:
            node.retrieve()
        self.assertEqual(len(nodes)+1, api.cache.hits)
        self.assertEqual(len(nodes)+2, api.cache.misses)
        api.cache.invalidate()
        self.assertEqual(0, api.stats['conditional'])
        for node in nodes:
            node.retrieve()
        self.assertEqual(len(nodes), api.stats['conditional'])
        api.cache.remove()
        for node in nodes:
            node.retrieve()
        self.assertEqual(len(nodes), api.stats['conditional'])
        self.assertEqual((2*len(nodes))+1, api.cache.hits)
        self.assertEqual((2*len(nodes))+2, api.cache.misses)
