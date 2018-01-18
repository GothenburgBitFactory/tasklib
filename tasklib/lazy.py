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
        return getattr(self, name)

    def __eq__(self, other):
        if other and other['uuid']:
            # For saved Tasks, just define equality by equality of uuids
            return self['uuid'] == other['uuid']

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return self['uuid'].__hash__()

    def __repr__(self):
        return 'LazyUUIDTask: {0}'.format(self._uuid)

    def __copy__(self):
        return LazyUUIDTask(self._tw, self._uuid)

    def __deepcopy__(self, memo):
        return LazyUUIDTask(self._tw, self._uuid)

    @property
    def saved(self):
        """
        Implementation of the 'saved' property. Always returns True.
        """
        return True

    @property
    def _modified_fields(self):
        return set()

    @property
    def modified(self):
        return False

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
            return getattr(self, name)

    def __repr__(self):
        return 'LazyUUIDTaskSet([{0}])'.format(', '.join(self._uuids))

    def __eq__(self, other):
        return set(t['uuid'] for t in other) == self._uuids

    def __ne__(self, other):
        return not (self == other)

    def __contains__(self, task):
        return task['uuid'] in self._uuids

    def __len__(self):
        return len(self._uuids)

    def __iter__(self):
        for uuid in self._uuids:
            yield LazyUUIDTask(self._tw, uuid)

    def __sub__(self, other):
        return self.difference(other)

    def __isub__(self, other):
        return self.difference_update(other)

    def __rsub__(self, other):
        return LazyUUIDTaskSet(
            self._tw,
            set(t['uuid'] for t in other) - self._uuids,
        )

    def __or__(self, other):
        return self.union(other)

    def __ior__(self, other):
        return self.update(other)

    def __ror__(self, other):
        return self.union(other)

    def __xor__(self, other):
        return self.symmetric_difference(other)

    def __ixor__(self, other):
        return self.symmetric_difference_update(other)

    def __rxor__(self, other):
        return self.symmetric_difference(other)

    def __and__(self, other):
        return self.intersection(other)

    def __iand__(self, other):
        return self.intersection_update(other)

    def __rand__(self, other):
        return self.intersection(other)

    def __le__(self, other):
        return self.issubset(other)

    def __ge__(self, other):
        return self.issuperset(other)

    def issubset(self, other):
        return all([task in other for task in self])

    def issuperset(self, other):
        return all([task in self for task in other])

    def union(self, other):
        return LazyUUIDTaskSet(
            self._tw,
            self._uuids | set(t['uuid'] for t in other),
        )

    def intersection(self, other):
        return LazyUUIDTaskSet(
            self._tw,
            self._uuids & set(t['uuid'] for t in other),
        )

    def difference(self, other):
        return LazyUUIDTaskSet(
            self._tw,
            self._uuids - set(t['uuid'] for t in other),
        )

    def symmetric_difference(self, other):
        return LazyUUIDTaskSet(
            self._tw,
            self._uuids ^ set(t['uuid'] for t in other),
        )

    def update(self, other):
        self._uuids |= set(t['uuid'] for t in other)
        return self

    def intersection_update(self, other):
        self._uuids &= set(t['uuid'] for t in other)
        return self

    def difference_update(self, other):
        self._uuids -= set(t['uuid'] for t in other)
        return self

    def symmetric_difference_update(self, other):
        self._uuids ^= set(t['uuid'] for t in other)
        return self

    def add(self, task):
        self._uuids.add(task['uuid'])

    def remove(self, task):
        self._uuids.remove(task['uuid'])

    def pop(self):
        return self._uuids.pop()

    def clear(self):
        self._uuids.clear()

    def replace(self):
        """
        Performs conversion to the regular TaskQuerySet object, referenced by
        the stored UUIDs.
        """

        replacement = self._tw.tasks.filter(' '.join(self._uuids))
        self.__class__ = replacement.__class__
        self.__dict__ = replacement.__dict__
