import unittest

from orm.api import Api
from orm.resources import Resource, ResourceSet

from .utils import login, random_ascii


class ResourceTests(unittest.TestCase):
    def setUp(self):
        login(self)
        self.rand = random_ascii(10)
    
    def test_instantiate(self):
        data = dict(name='drained', surname='water')
        self.resource = Resource(**data)
        self.assertIsNone(self.resource.uri)
        self.assertEqual(data, self.resource.serialize())
    
    def test_save(self):
        self.test_instantiate()
        self.assertRaises(TypeError, self.resource.save)
        self.resource.bind(self.api.nodes)
        self.assertRaises(Api.ResponseStatusError, self.resource.save)
    
    def test_retrieve(self):
        groups = self.api.groups.retrieve()
        self.group = groups[0]
        self.group.name
    
    def test_create(self):
        self.test_retrieve()
        name = 'RandomTest-%s' % self.rand
        node = Resource(name=name, group=self.group)
        node.bind(self.api.nodes)
        node.save()
        self.assertIsNotNone(node.uri)
        self.assertLess(15, len(node.serialize()))
        self.node = node
        self.retrieved = self.api.retrieve(node.uri)
        self.assertEqual(self.retrieved, node)
    
    def test_serialize(self):
        self.test_create()
        response = self.api.get(self.retrieved.uri)
        raw = self.api.serialize_response(response.content)
        self.assertDictEqual(raw, self.retrieved.serialize())
    
    def test_delete(self):
        self.test_create()
        self.node.delete()
        self.assertRaises(self.api.ResponseStatusError, self.api.retrieve, self.node.uri)
    
    def test_manager(self):
        self.test_create()
        self.node.nodes.create
    
    def test_related(self):
        self.test_create()
        self.assertTrue(self.node.group.name)
    
    def test_conditional_request(self):
        self.test_create()
        self.node.retrieve()
        self.assertEqual(0, self.node.api.stats['conditional'])
        self.node.retrieve()
        self.assertEqual(1, self.node.api.stats['conditional'])


class CollectionTests(unittest.TestCase):
    def setUp(self):
        login(self)
        self.NUM_NODES = 5
        self.group = self.api.groups.retrieve()[0]
        self.rand = random_ascii(10)
        for i in range(0, self.NUM_NODES):
            name = 'RandomTest-%s-%d' % (self.rand, i)
            self.api.nodes.create(name=name, group=self.group)
        self.nodes = self.api.nodes.retrieve()
    
    def tearDown(self):
        nodes = self.nodes.filter(name__startswith='RandomTest-%s-' % self.rand)
        nodes.destroy()
    
    def test_retrieve(self):
        self.assertLessEqual(self.NUM_NODES, len(self.nodes))
        self.nodes.retrieve()
        self.assertEqual(len(self.nodes), self.api.stats['async'])
    
    def test_simple_filter(self):
        some = self.nodes.filter(name__startswith='RandomTest-%s-' % self.rand)
        self.assertEqual(self.NUM_NODES, len(some))
    
    def test_complex_filter(self):
        nodes = self.nodes.filter(group__user_roles__user__name__exact=self.group.name,
                name__startswith='RandomTest-%s-' % self.rand, id__gte=1)
        some = nodes.filter(name__startswith='RandomTest-%s-' % self.rand)
        self.assertEqual(len(some), len(nodes))
    
    def test_exclude(self):
        nodes = self.nodes.filter(name__startswith='RandomTest-%s-' % self.rand)
        nodes = nodes.exclude(name='RandomTest-%s-1' % self.rand)
        self.assertEqual(self.NUM_NODES-1, len(nodes))
    
    def test_destroy(self):
        for i in range(0, self.NUM_NODES):
            name = 'RandomTestDestroy-%s-%d' % (self.rand, i)
            self.api.nodes.create(name=name, group=self.group)
        nodes = self.api.nodes.retrieve()
        nodes = nodes.filter(name__startswith='RandomTestDestroy-%s-' % self.rand)
        successes, failures = nodes.destroy()
        self.assertEqual(0, len(failures))
        nodes = self.api.nodes.retrieve()
        nodes = nodes.filter(name__startswith='RandomTestDestroy-%s-' % self.rand)
        self.assertEqual(0, len(nodes))
    
    def test_values_list(self):
        nodes = self.nodes.filter(name__startswith='RandomTest-%s-' % self.rand)
        names = nodes.values_list('name')
        self.assertEqual(self.NUM_NODES, len(names))
        self.assertEqual(self.NUM_NODES, len(names.distinct()))
        names = nodes.values_list('group__name')
        self.assertEqual(self.NUM_NODES, len(names))
        self.assertEqual(names[0], self.group.name)
        self.assertEqual(1, len(names.distinct()))
    
    def test_get(self):
        nodes = self.nodes.filter(name__startswith='RandomTest-%s-' % self.rand)
        node_id = nodes[0].id
        node = nodes.get(id=node_id)
        self.assertEqual(node_id, node.id)
    
    def test_update(self):
        nodes = self.nodes.filter(name__startswith='RandomTest-%s-' % self.rand)
        description = 'RandomDescription-%s' % self.rand
        nodes.update(description=description)
        for node in nodes:
            self.assertEqual(description, node.description)
        nodes.retrieve()
        for node in nodes:
            self.assertEqual(description, node.description)
    
    def test_retrieve_related(self):
        self.nodes.retrieve_related('group')
        groups = self.nodes.values_list('group').distinct()
        self.assertEqual(len(groups), self.api.stats['async'])
        self.nodes.retrieve_related('group__user_roles__user')
        user_roles = groups.values_list('user_roles').distinct()
        users = user_roles.values_list('user').distinct()
        current = self.api.stats['get']
        users[0].name
        self.assertEqual(current, self.api.stats['get'])
        self.assertEqual(2*len(groups)+len(users), self.api.stats['async'])
        self.nodes.retrieve_related('group__user_roles__user', soft=True)
        self.assertEqual(current, self.api.stats['get'])


class RelatedCollectionTests(unittest.TestCase):
    def setUp(self):
        login(self)
        self.NUM_NODES = 5
        self.group = self.api.groups.retrieve()[0]
        self.rand = random_ascii(10)
        template = self.api.templates.retrieve()[0]
        self.slice = self.api.slices.create(name='TestSlice-%s' % self.rand,
                group=self.group, template=template)
        self.node = self.api.nodes.create(group=self.group, name='TestNode-%s' % self.rand)
    
    def tearDown(self):
        self.node.delete()
        self.slice.delete()
    
    def test_create(self):
        sliver = self.node.slivers.create(slice=self.slice)
        self.assertEqual(self.slice, sliver.slice)
        self.assertEqual(self.node, sliver.node)
        self.assertEqual(1, len(self.node.slivers))
    
    def test_retrieve(self):
        self.api.slivers.create(slice=self.slice, node=self.node)
        self.assertEqual(0, len(self.node.slivers))
        self.node.slivers.retrieve()
        self.assertEqual(1, len(self.node.slivers))
    
    def test_destroy(self):
        self.group.retrieve()
        self.assertLessEqual(1, len(self.group.nodes))
        self.group.nodes.destroy()
        self.assertLessEqual(1, len(self.group.nodes))
        self.group.retrieve()
        self.assertEqual(0, len(self.group.nodes))
        self.node = self.api.nodes.create(group=self.group, name='TestNode-%s' % self.rand)
    
    def test_append(self):
        sliver = self.api.slivers.create(slice=self.slice, node=self.node)
        template = self.api.templates.retrieve()[0]
        other_slice = self.api.slices.create(name='TestSlice2-%s' % self.rand,
                group=self.group, template=template)
        other_slice.slivers.append(sliver)
        sliver.save()
        other_slice.retrieve()
        self.assertEqual(sliver.uri, other_slice.slivers[0].uri)
        other_slice.delete()


class ResourceSetTests(unittest.TestCase):
    def setUp(self):
        login(self)
        self.group = self.api.groups.retrieve()[0]
    
    def test_uniquenes(self):
        groups = ResourceSet([self.group, self.group, self.group, self.group])
        self.assertEqual(1, len(groups))
