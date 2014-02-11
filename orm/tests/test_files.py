from __future__ import unicode_literals

import io
import unittest

from orm.api import Api

from .utils import login, random_ascii


class FileHandlerTests(unittest.TestCase):
    def setUp(self):
        login(self)
    
    def test_file_handler(self):
        uri = 'http://microsoft.com/templates/Windows98-ServicePack-2.tgz'
        sha256 = '76a71abd164ce3b149c84d52a4bd313e74cae75539bd5c10628b784792ba039c'
        name = 'RandomTemplate-%s' % random_ascii(10)
        template = self.api.templates.create(name=name, image_uri=uri, type='debian',
                image_sha256=sha256, is_active=True, node_archs=["i686"])
        fake_file = io.StringIO()
        content = unicode(random_ascii(100))
        fake_file.name = 'Windows98-ServicePack-2.tgz'
        fake_file.write(content)
        fake_file.seek(0)
        template.upload_image(fake_file)
        template.retrieve()
        template.image.retrieve()
        template.image.validate_sha256()
        self.assertEqual(content, template.image.content)
        template.delete()
        template.image.retrieve(save_to='/dev/shm/')
        with open(template.image.file.name, 'ru') as f:
            self.assertEqual(content, f.read())
        template.image.validate_sha256()
        async = template.image.retrieve(async=True)
        async.get()
        template.image.sha256 += '1'
        self.assertRaises(ValueError, template.image.validate_sha256)
