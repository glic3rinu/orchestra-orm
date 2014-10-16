import os
from setuptools import setup, find_packages


# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

packages = find_packages('.')


setup(
    name = 'orchestra-orm',
    version = '0.2',
    packages = packages,
    include_package_data = True,
    license = 'BSD License',
    description = ('high level Python library for easily interacting with Django-Orchestra REST API using object oriented concepts'),
    url = 'https://github.com/glic3rinu/orchestra-orm',
    author = 'Marc Aymerich',
    author_email = 'marcay@pangea.org',
    install_requires=[
        'requests',
        'gevent',
    ],
    classifiers = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
