import cPickle


class CacheDict(dict):
    """ Key-value store """
    hits = 0
    misses = 0
    
    def get(self, args, kwargs):
        try:
            value = self[(args, cPickle.dumps(kwargs))]
        except KeyError as e:
            self.misses += 1
            raise e
        else:
            self.hits += 1
            value.accesses += 1
            return value
    
    def put(self, args, value):
        self[(args[0], cPickle.dumps(args[1]))] = value
        value.is_valid = True
        value.accesses = 0
    
    def invalidate(self, url=None):
        for key, response in self.iteritems():
            if not url or (url and key[0] == url):
                response.is_valid = False
    
    def remove(self, url=None, accesses=0):
        for key, response in self.items():
            if not url or (url and key[0] == url):
                self.pop(key)
