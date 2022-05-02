import json
import logging
from os import path
from typing import Any, Dict
from types import ModuleType

import yaml


logger = logging.getLogger(__name__)


def load_resource(filename: str, resource_module: ModuleType) -> str:
    logger.debug("Loading a resource file %r.%s", resource_module, filename)
    with open(get_resource_path(filename, resource_module), "r", encoding="utf8") as fd:
        return fd.read()


def get_resource_path(filename: str, resource_module: ModuleType) -> str:
    logger.debug(
        "Obtaining the full path of a resource file %r.%s", resource_module, filename
    )
    return path.join(path.dirname(resource_module.__file__), filename)


def yaml_to_dict(yaml_str: str) -> Dict[Any, Any]:
    return yaml.safe_load(yaml_str)


def json_to_dict(json_str: str) -> Dict[Any, Any]:
    return json.loads(json_str)
