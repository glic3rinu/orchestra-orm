import unittest

from .utils import login

from orm import relations as rel
from orm.managers import Manager


class ManagerTests(unittest.TestCase):
    def setUp(self):
        login(self)
    
    def test_access(self):
        node = self.api.nodes.retrieve()[0]
        self.assertIs(Manager, type(self.api.nodes))
        self.assertIs(Manager, type(node.reboot))
        self.assertIs(Manager, type(node.nodes))
    
    def test_register(self):
        group = self.api.groups.retrieve()[0]
        
        @Manager.register(rel.SERVER_NODES)
        def create(manager, url, *args, **kwargs):
            return 'created'
        self.assertEqual('created', self.api.nodes.create())
        self.assertEqual('created', group.nodes.create())
        Manager.unregister(rel.SERVER_NODES, create)
        
        @Manager.register(rel.SERVER_NODES)
        def random_method(manager, url, *args, **kwargs):
            return 'randomized'
        self.assertEqual('randomized', self.api.nodes.random_method())
        self.assertEqual('randomized', group.nodes.random_method())
        Manager.unregister(rel.SERVER_NODES, random_method)
        
        #TODO how to register a method to a node? node.method() ?
        #TODO nodes.methos() with nodes being a collection
        #TODO nodeset.bulk(method, *args, **kwargs)
