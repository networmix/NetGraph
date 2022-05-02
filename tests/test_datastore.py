from copy import deepcopy
from collections import namedtuple
from dataclasses import dataclass, fields
from operator import getitem
from typing import Any, ClassVar, Dict, List

from ngraph.datastore import DataStore, DataStoreDataClass


@dataclass
class DataStoreDataTest(DataStoreDataClass):
    index: ClassVar[List[str]] = ["tst_index"]
    tst_index: str
    tst_column: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            field.name: deepcopy(getattr(self, field.name))
            for field in fields(self)
            if not field.name.startswith("_")
        }


def test_add_item_1():
    ds = DataStore(DataStoreDataTest)
    data = DataStoreDataTest("42", "TestData")

    ds.add(data)
    assert ds.df.loc["42"].to_dict() == data.to_dict()


def test_contains_1():
    ds = DataStore(DataStoreDataTest)
    data = DataStoreDataTest("42", "TestData")

    ds.add(data)
    assert "42" in ds
    assert "41" not in ds


def test_get_item_1():
    ds = DataStore(DataStoreDataTest)
    data = DataStoreDataTest("42", "TestData")

    ds.add(data)
    assert data == ds["42"]


def test_iter_1():
    ds = DataStore(DataStoreDataTest)
    data_vector = [
        DataStoreDataTest("1", "TestData1"),
        DataStoreDataTest("2", "TestData2"),
        DataStoreDataTest("3", "TestData3"),
    ]

    for data in data_vector:
        ds.add(data)

    for idx, data in enumerate(ds):
        assert data == namedtuple(
            DataStoreDataTest.__name__, data_vector[idx].to_dict()
        )(**data_vector[idx].to_dict())


def test_get_data_1():
    ds = DataStore(DataStoreDataTest)
    data_vector = [
        DataStoreDataTest("1", "TestData1"),
        DataStoreDataTest("2", "TestData2"),
        DataStoreDataTest("3", "TestData3"),
    ]

    for data in data_vector:
        ds.add(data)

    assert ds.get_data("2", "tst_column") == "TestData2"


def test_update_data_1():
    ds = DataStore(DataStoreDataTest)
    data_vector = [
        DataStoreDataTest("1", "TestData1"),
        DataStoreDataTest("2", "TestData2"),
        DataStoreDataTest("3", "TestData3"),
    ]

    for data in data_vector:
        ds.add(data)

    ds.update_data("2", "tst_column", "TestData42")
    assert ds.df.loc["2"]["tst_column"] == "TestData42"
