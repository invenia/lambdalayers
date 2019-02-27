import os
import zipfile
from io import BytesIO
from pathlib import Path

import boto3
import pytest
import requests

from lambdalayers.cli import (
    _permission_ids,
    _read_local_layer,
    list_layers,
    list_versions,
    publish_layer,
)


DIR = Path(__file__).resolve().parent
STACKNAME = os.getenv("STACKNAME")


def layer_names(layers, prefix=""):
    return [
        layer["LayerName"] for layer in layers if layer["LayerName"].startswith(prefix)
    ]


class TestUtils(object):
    def test_permission_ids(self):
        session = boto3.session.Session()
        my_organization = session.client("organizations").describe_organization()[
            "Organization"
        ]["Id"]
        my_account = session.client("sts").get_caller_identity()["Account"]
        assert _permission_ids(session, "123", None, False, False) == ("123", None)
        assert _permission_ids(session, "123", "123", False, False) == ("*", "123")
        assert _permission_ids(session, None, None, True, False) == (my_account, None)
        assert _permission_ids(session, None, None, False, True) == (
            "*",
            my_organization,
        )
        with pytest.raises(ValueError):
            _permission_ids(session, None, None, False, False)

    def test_read_local_layer(self):
        local_path = DIR / "test_layer"
        files, requirements_file = _read_local_layer(DIR / "test_layer")
        assert local_path / Path(".build/package/foo.py") not in files
        assert local_path / Path("requirements.txt") not in files
        assert local_path / Path("foo.py") in files
        assert local_path / Path("bar") in files
        assert len(files) == 2
        assert requirements_file == local_path / Path("requirements.txt")


class TestLayers(object):
    def test_publish(self):
        session = boto3.session.Session()

        layer_name = f"{STACKNAME}-TestLayer1"
        layer_description = "TestVersion1"
        published = publish_layer(
            session,
            layer_name,
            layer_description,
            DIR / "test_layer",
            None,  # default build dir
            ["python3.6"],
            _permission_ids(session, None, None, True, False)[0],  # my account
        )

        assert published["Description"] == layer_description
        assert published["CompatibleRuntimes"] == ["python3.6"]

        # test local package.zip
        layer_zip = zipfile.ZipFile(DIR / "test_layer" / ".build" / "package.zip")
        layer_file_set = frozenset(layer_zip.namelist())
        assert "python/foo.py" in layer_file_set
        assert "python/bar/__init__.py" in layer_file_set
        assert "python/requirements.txt" not in layer_file_set
        assert "python/scrapy/__init__.py" in layer_file_set

        # test remote zip
        resp = requests.get(published["Content"]["Location"])
        layer_zip = zipfile.ZipFile(BytesIO(resp.content))
        layer_file_set = frozenset(layer_zip.namelist())
        assert "python/foo.py" in layer_file_set
        assert "python/bar/__init__.py" in layer_file_set
        assert "python/requirements.txt" not in layer_file_set
        assert "python/scrapy/__init__.py" in layer_file_set

        layers = list_layers(session)
        assert layer_names(layers) == [layer_name]

        layers = list_layers(session, "python3.6")
        assert layer_names(layers) == [layer_name]

        layers = list_layers(session, "python3.7")
        assert layer_names(layers) == []

        versions = list(list_versions(session, layer_name))
        assert len(versions) == 1
        assert versions[0]["Description"] == layer_description

        versions = list(list_versions(session, layer_name, "python3.6"))
        assert len(versions) == 1
        assert versions[0]["Description"] == layer_description

        versions = list(list_versions(session, layer_name, "python3.7"))
        assert versions == []

    @classmethod
    def teardown_class(cls):
        session = boto3.session.Session()
        client = session.client("lambda")
        layers = list_layers(session)

        for layer in layers:
            layer_name = layer["LayerName"]
            if layer_name.startswith((f"{STACKNAME}-TestLayer", "None-TestLayer")):
                versions = list_versions(session, layer["LayerArn"])
                for version in versions:
                    print(f"deleting {layer_name}:{version}")
                    client.delete_layer_version(
                        LayerName=layer_name, VersionNumber=version["Version"]
                    )
