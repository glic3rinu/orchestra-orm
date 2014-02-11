import hashlib
import io
import os

import gevent

from . import status


class FileHandler(object):
    """
    Handles file objects with convenient methods.
    
    Files are never loaded into memory and asynchronous downloading is supported
    """
    def __init__(self, parent, field_name):
        self.parent = parent
        self.field_name = field_name
        self.file = None
        self.content = None
    
    @property
    def sha256(self):
        return getattr(self.parent, '%s_sha256' % self.field_name)
    
    @sha256.setter
    def sha256(self, value):
        setattr(self.parent, '%s_sha256' % self.field_name, value)
    
    @property
    def uri(self):
        return getattr(self.parent, '%s_uri' % self.field_name)
    
    @uri.setter
    def uri(self, value):
        setattr(self.parent, '%s_uri' % self.field_name, value)
    
    def retrieve(self, save_to=None, async=False):
        def download(self, save_to=save_to):
            response = self.parent.api.get(self.uri, stream=True)
            self.parent.api.validate_response(response, status.HTTP_200_OK)
            if save_to:
                if save_to.endswith('/'):
                    # filename not provided
                    file_name = response.url.split('/')[-1]
                    save_to = os.path.join(save_to, file_name)
                with open(save_to, 'wb') as self.file:
                    for chunk in response.iter_content():
                        self.file.write(chunk)
            else:
                self.content = response.content
            self.validate_sha256()
        
        if async:
            self.glet = gevent.spawn(download, self, save_to=save_to)
            self.parent.api.stats['async'] += 1
            return self.glet
        return download(self, save_to=save_to)
    
    def validate_sha256(self):
        if self.file is None and self.content is None:
            raise IOError('the file must be retrieved first')
        if self.file is None:
            sha256 = hashlib.sha256(self.content)
        else:
            block_size=2**20
            sha256 = hashlib.sha256()
            with open(self.file.name, 'rb') as self.file:
                for chunk in iter(lambda: self.file.read(block_size), b''):
                    sha256.update(chunk)
        hexdigest = sha256.hexdigest()
        if self.sha256 != hexdigest:
            raise ValueError("'%s' != '%s'" % (self.sha256, hexdigest))
