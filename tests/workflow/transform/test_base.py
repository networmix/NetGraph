import pytest

from ngraph.workflow.transform.base import (
    TRANSFORM_REGISTRY,
    NetworkTransform,
    register_transform,
)


def test_registry_contains_transforms():
    assert "EnableNodes" in TRANSFORM_REGISTRY
    assert "DistributeExternalConnectivity" in TRANSFORM_REGISTRY


def test_create_known_transform():
    transform = NetworkTransform.create("EnableNodes", path="dummy", count=1)
    from ngraph.workflow.transform.enable_nodes import EnableNodesTransform

    assert isinstance(transform, EnableNodesTransform)


def test_create_unknown_transform():
    with pytest.raises(KeyError) as exc:
        NetworkTransform.create("NoSuch", foo=1)
    assert "Unknown transform 'NoSuch'" in str(exc.value)


def test_register_duplicate_name_raises():
    with pytest.raises(ValueError):

        @register_transform("EnableNodes")
        class DummyTransform(NetworkTransform):
            def apply(self, scenario):
                pass
