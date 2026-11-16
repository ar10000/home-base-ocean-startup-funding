import uuid

from home_base.core.ids import new_id


def test_new_id_is_a_standard_uuid_version_7() -> None:
    value = new_id()
    assert type(value) is uuid.UUID
    assert value.version == 7


def test_new_ids_are_unique_and_sort_by_creation() -> None:
    ids = [new_id() for _ in range(1000)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)
