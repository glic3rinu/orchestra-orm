import os
import string
import random

from orm.api import Api


def login(self):
    self.api = Api(os.environ['CONFINE_SERVER_API'])
    self.api.username = os.environ['CONFINE_USER']
    self.api.password = os.environ['CONFINE_PASSWORD']
    self.api.login()


def random_ascii(length):
    return ''.join([random.choice(string.hexdigits) for i in range(0, length)])
