class ResponseStatusError(Exception):
    """ unexpected status code """


class DoesNotExist(Exception):
    """ raised when get() without objects """


class MultipleObjects(Exception):
    """ raised when get() returns multiple objects """
