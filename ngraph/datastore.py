from __future__ import annotations
from copy import deepcopy
from dataclasses import fields
from typing import Any, Dict, Iterator, List, Protocol, Type

import pandas as pd
from dacite import from_dict


class DataStoreDataClass(Protocol):
    __dataclass_fields__: Dict[str, Any]
    index: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            field.name: deepcopy(getattr(self, field.name))
            for field in fields(self)
            if not field.name.startswith("_")
        }

    def get_index(self) -> Any:
        return tuple(getattr(self, idx_field) for idx_field in self.index)


class DataStore:
    def __init__(self, record_type: Type[DataStoreDataClass]) -> None:
        self._record_type: Type[DataStoreDataClass] = record_type
        self.df: pd.DataFrame = pd.DataFrame(
            columns=[field.name for field in fields(record_type)]
        )
        self.df.set_index(record_type.index, inplace=True, drop=False)

    def __iter__(self) -> Iterator:
        """
        Making DataStore iterable by rows of the dataframe.
        Each entry is a named tuple of all columns excluding index.
        """
        return self.df.itertuples(index=False, name=self._record_type.__name__)

    def __contains__(self, index: Any) -> bool:
        """
        True if dataframe contains given index and False otherwise.
        """
        return index in self.df.index

    def __getitem__(self, index: Any) -> DataStoreDataClass:
        return from_dict(
            data_class=self._record_type, data=self.df.loc[index].to_dict()
        )

    def add(self, data_obj: DataStoreDataClass) -> None:
        self.df.loc[data_obj.get_index()] = data_obj.to_dict()

    def update_data(self, index: Any, column: str, data: Any) -> None:
        self.df.at[index, column] = data

    def get_data(self, index: Any, column: str) -> Any:
        return self.df.at[index, column]
