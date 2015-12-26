import datetime
import importlib
import json
import pytz
import six
import tzlocal


from .lazy import LazyUUIDTaskSet, LazyUUIDTask

DATE_FORMAT = '%Y%m%dT%H%M%SZ'
local_zone = tzlocal.get_localzone()


class SerializingObject(object):
    """
    Common ancestor for TaskResource & TaskWarriorFilter, since they both
    need to serialize arguments.

    Serializing method should hold the following contract:
      - any empty value (meaning removal of the attribute)
        is deserialized into a empty string
      - None denotes a empty value for any attribute

    Deserializing method should hold the following contract:
      - None denotes a empty value for any attribute (however,
        this is here as a safeguard, TaskWarrior currently does
        not export empty-valued attributes) if the attribute
        is not iterable (e.g. list or set), in which case
        a empty iterable should be used.

    Normalizing methods should hold the following contract:
      - They are used to validate and normalize the user input.
        Any attribute value that comes from the user (during Task
        initialization, assignign values to Task attributes, or
        filtering by user-provided values of attributes) is first
        validated and normalized using the normalize_{key} method.
      - If validation or normalization fails, normalizer is expected
        to raise ValueError.
    """

    def __init__(self, backend):
        self.backend = backend

    def _deserialize(self, key, value):
        hydrate_func = getattr(self, 'deserialize_{0}'.format(key),
                               lambda x: x if x != '' else None)
        return hydrate_func(value)

    def _serialize(self, key, value):
        dehydrate_func = getattr(self, 'serialize_{0}'.format(key),
                                 lambda x: x if x is not None else '')
        return dehydrate_func(value)

    def _normalize(self, key, value):
        """
        Use normalize_<key> methods to normalize user input. Any user
        input will be normalized at the moment it is used as filter,
        or entered as a value of Task attribute.
        """

        # None value should not be converted by normalizer
        if value is None:
            return None

        normalize_func = getattr(self, 'normalize_{0}'.format(key),
                                 lambda x: x)

        return normalize_func(value)

    def timestamp_serializer(self, date):
        if not date:
            return ''

        # Any serialized timestamp should be localized, we need to
        # convert to UTC before converting to string (DATE_FORMAT uses UTC)
        date = date.astimezone(pytz.utc)

        return date.strftime(DATE_FORMAT)

    def timestamp_deserializer(self, date_str):
        if not date_str:
            return None

        # Return timestamp localized in the local zone
        naive_timestamp = datetime.datetime.strptime(date_str, DATE_FORMAT)
        localized_timestamp = pytz.utc.localize(naive_timestamp)
        return localized_timestamp.astimezone(local_zone)

    def serialize_entry(self, value):
        return self.timestamp_serializer(value)

    def deserialize_entry(self, value):
        return self.timestamp_deserializer(value)

    def normalize_entry(self, value):
        return self.datetime_normalizer(value)

    def serialize_modified(self, value):
        return self.timestamp_serializer(value)

    def deserialize_modified(self, value):
        return self.timestamp_deserializer(value)

    def normalize_modified(self, value):
        return self.datetime_normalizer(value)

    def serialize_start(self, value):
        return self.timestamp_serializer(value)

    def deserialize_start(self, value):
        return self.timestamp_deserializer(value)

    def normalize_start(self, value):
        return self.datetime_normalizer(value)

    def serialize_end(self, value):
        return self.timestamp_serializer(value)

    def deserialize_end(self, value):
        return self.timestamp_deserializer(value)

    def normalize_end(self, value):
        return self.datetime_normalizer(value)

    def serialize_due(self, value):
        return self.timestamp_serializer(value)

    def deserialize_due(self, value):
        return self.timestamp_deserializer(value)

    def normalize_due(self, value):
        return self.datetime_normalizer(value)

    def serialize_scheduled(self, value):
        return self.timestamp_serializer(value)

    def deserialize_scheduled(self, value):
        return self.timestamp_deserializer(value)

    def normalize_scheduled(self, value):
        return self.datetime_normalizer(value)

    def serialize_until(self, value):
        return self.timestamp_serializer(value)

    def deserialize_until(self, value):
        return self.timestamp_deserializer(value)

    def normalize_until(self, value):
        return self.datetime_normalizer(value)

    def serialize_wait(self, value):
        return self.timestamp_serializer(value)

    def deserialize_wait(self, value):
        return self.timestamp_deserializer(value)

    def normalize_wait(self, value):
        return self.datetime_normalizer(value)

    def serialize_annotations(self, value):
        value = value if value is not None else []

        # This may seem weird, but it's correct, we want to export
        # a list of dicts as serialized value
        serialized_annotations = [json.loads(annotation.export_data())
                                  for annotation in value]
        return serialized_annotations if serialized_annotations else ''

    def deserialize_annotations(self, data):
        task_module = importlib.import_module('tasklib.task')
        TaskAnnotation = getattr(task_module, 'TaskAnnotation')
        return [TaskAnnotation(self, d) for d in data] if data else []

    def serialize_tags(self, tags):
        return ','.join(tags) if tags else ''

    def deserialize_tags(self, tags):
        if isinstance(tags, six.string_types):
            return set(tags.split(',')) if tags else set()
        return set(tags or [])

    def serialize_parent(self, parent):
        return parent['uuid'] if parent else ''

    def deserialize_parent(self, uuid):
        return LazyUUIDTask(self.backend, uuid) if uuid else None

    def serialize_depends(self, value):
        # Return the list of uuids
        value = value if value is not None else set()

        if isinstance(value, LazyUUIDTaskSet):
            return ','.join(value._uuids)
        else:
            return ','.join(task['uuid'] for task in value)

    def deserialize_depends(self, raw_uuids):
        raw_uuids = raw_uuids or []  # Convert None to empty list

        if not raw_uuids:
            return set()

        # TW 2.4.4 encodes list of dependencies as a single string
        if type(raw_uuids) is not list:
            uuids = raw_uuids.split(',')
        # TW 2.4.5 and later exports them as a list, no conversion needed
        else:
            uuids = raw_uuids

        return LazyUUIDTaskSet(self.backend, uuids)

    def datetime_normalizer(self, value):
        """
        Normalizes date/datetime value (considered to come from user input)
        to localized datetime value. Following conversions happen:

        naive date -> localized datetime with the same date, and time=midnight
        naive datetime -> localized datetime with the same value
        localized datetime -> localized datetime (no conversion)
        """

        if (
            isinstance(value, datetime.date)
            and not isinstance(value, datetime.datetime)
        ):
            # Convert to local midnight
            value_full = datetime.datetime.combine(value, datetime.time.min)
            localized = local_zone.localize(value_full)
        elif isinstance(value, datetime.datetime):
            if value.tzinfo is None:
                # Convert to localized datetime object
                localized = local_zone.localize(value)
            else:
                # If the value is already localized, there is no need to change
                # time zone at this point. Also None is a valid value too.
                localized = value
        elif isinstance(value, six.string_types):
            localized = self.backend.convert_datetime_string(value)
        else:
            raise ValueError("Provided value could not be converted to "
                             "datetime, its type is not supported: {}"
                             .format(type(value)))

        return localized

    def normalize_uuid(self, value):
        # Enforce sane UUID
        if not isinstance(value, six.string_types) or value == '':
            raise ValueError("UUID must be a valid non-empty string, "
                             "not: {}".format(value))

        return value
