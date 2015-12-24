"""
Provides lazy implementations for Task and TaskQuerySet.
"""


class LazyUUIDTask(object):
    """
    A lazy wrapper around Task object, referenced by UUID.

    - Supports comparison with LazyUUIDTask or Task objects (equality by UUIDs)
    - If any attribute other than 'uuid' requested, a lookup in the
      backend will be performed and this object will be replaced by a proper
      Task object.
    """

    def __init__(self, tw, uuid):
        self._tw = tw
        self._uuid = uuid

    def __getitem__(self, key):
        # LazyUUIDTask does not provide anything else other than 'uuid'
        if key is 'uuid':
            return self._uuid
        else:
            self.replace()
            return self[key]

    def __getattr__(self, name):
        # Getattr is called only if the attribute could not be found using
        # normal means
        self.replace()
        return self.name

    def __eq__(self, other):
        if other['uuid']:
            # For saved Tasks, just define equality by equality of uuids
            return self['uuid'] == other['uuid']

    def __hash__(self):
        return self['uuid'].__hash__()

    def __repr__(self):
        return "LazyUUIDTask: {0}".format(self._uuid)

    @property
    def saved(self):
        """
        Implementation of the 'saved' property. Always returns True.
        """
        return True

    def replace(self):
        """
        Performs conversion to the regular Task object, referenced by the
        stored UUID.
        """

        replacement = self._tw.tasks.get(uuid=self._uuid)
        self.__class__ = replacement.__class__
        self.__dict__ = replacement.__dict__


class LazyUUIDTaskSet(object):
    """
    A lazy wrapper around TaskQuerySet object, for tasks referenced by UUID.

    - Supports 'in' operator with LazyUUIDTask or Task objects
    - If iteration over the objects in the LazyUUIDTaskSet is requested, the
      LazyUUIDTaskSet will be converted to QuerySet and evaluated
    """

    def __init__(self, tw, uuids):
        self._tw = tw
        self._uuids = set(uuids)

    def __getattr__(self, name):
        # Getattr is called only if the attribute could not be found using
        # normal means

        if name.startswith('__'):
            # If some internal method was being search, do not convert
            # to TaskQuerySet just because of that
            raise AttributeError
        else:
            self.replace()
            return self.name

    def __repr__(self):
        return "LazyUUIDTaskSet([{0}])".format(', '.join(self._uuids))

    def __eq__(self, other):
        return set(t['uuid'] for t in other) == self._uuids

    def __contains__(self, task):
        return task['uuid'] in self._uuids

    def __len__(self):
        return len(self._uuids)

    def __iter__(self):
        for uuid in self._uuids:
            yield LazyUUIDTask(self._tw, uuid)

    def replace(self):
        """
        Performs conversion to the regular TaskQuerySet object, referenced by
        the stored UUIDs.
        """

        replacement = self._tw.tasks.filter(' '.join(self._uuids))
        self.__class__ = replacement.__class__
        self.__dict__ = replacement.__dict__
