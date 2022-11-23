import json
import os
import shutil
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import boto3
import docker
import pytest
import requests

import lambdalayers
from lambdalayers.api import (
    _permission_ids,
    _read_local_layer,
    build_layer,
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


@contextmanager
def public_tmp_dir(parent):
    tmpdir = Path(parent) / uuid.uuid4().hex
    tmpdir.mkdir(parents=True)
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def build_dir():
    build_dir = tempfile.mkdtemp(prefix="lambdalayers")
    yield Path(build_dir)
    shutil.rmtree(build_dir, ignore_errors=True)


@pytest.fixture
def layer_cleanup():
    yield None
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


class TestUtils(object):
    def test_version_exists(self):
        # largely here for test coverage of __init__.py
        assert hasattr(lambdalayers, "__version__")

    @pytest.mark.aws
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
    @pytest.mark.xfail
    def test_build_single_runtime(self, build_dir):
        package = build_layer(DIR / "test_layer", ["python3.7"], build_dir)
        with zipfile.ZipFile(package) as layer_zip:
            layer_file_set = frozenset(layer_zip.namelist())
            assert "python/foo.py" in layer_file_set
            assert "python/bar/__init__.py" in layer_file_set
            assert "python/requirements.txt" not in layer_file_set
            assert "python/scrapy/__init__.py" in layer_file_set

    @pytest.mark.xfail
    def test_build_compat_runtime(self, build_dir):
        package = build_layer(
            DIR / "test_compat_layer", ["python3.7", "python3.8"], build_dir
        )
        with zipfile.ZipFile(package) as layer_zip:
            layer_file_set = frozenset(layer_zip.namelist())
            assert "python/foo.py" in layer_file_set
            assert "python/bar/__init__.py" in layer_file_set
            assert "python/requirements.txt" not in layer_file_set
            assert "python/pg8000/__init__.py" in layer_file_set

    @pytest.mark.xfail
    def test_build_multi_runtime(self, build_dir):
        package = build_layer(
            DIR / "test_multi_layer", ["python3.7", "python3.8"], build_dir
        )
        with zipfile.ZipFile(package) as layer_zip:
            layer_file_set = frozenset(layer_zip.namelist())
            assert "python/psycopg2/__init__.py" not in layer_file_set
            assert "python/requirements.txt" not in layer_file_set
            python37_dir = "python/lib/python3.7/site-packages"
            python38_dir = "python/lib/python3.8/site-packages"
            assert f"{python37_dir}/psycopg2/__init__.py" in layer_file_set
            assert f"{python38_dir}/psycopg2/__init__.py" in layer_file_set
            assert (
                f"{python37_dir}/psycopg2/_psycopg.cpython-37m-x86_64-linux-gnu.so"
                in layer_file_set
            )
            assert (
                f"{python38_dir}/psycopg2/_psycopg.cpython-38m-x86_64-linux-gnu.so"
                in layer_file_set
            )

    @pytest.mark.xfail
    def test_run_lambda(self, build_dir):
        runtimes = ["python3.7", "python3.8", "python3.9"]
        package = build_layer(DIR / "test_multi_layer", runtimes, build_dir)

        with public_tmp_dir(DIR / ".tmp") as tmp_dir:
            with zipfile.ZipFile(package) as z:
                z.extractall(tmp_dir)

            for runtime in runtimes:
                client = docker.from_env()
                output_bytes = client.containers.run(
                    f"lambci/lambda:{runtime}",
                    mounts=[
                        docker.types.Mount(
                            "/var/task",
                            str(DIR / "test_lambda"),
                            type="bind",
                            read_only=True,
                        ),
                        docker.types.Mount(
                            "/opt", str(tmp_dir), type="bind", read_only=True
                        ),
                    ],
                    command="lambda_function.lambda_handler",
                )
                output = json.loads(output_bytes)
                assert any(runtime in path for path in output["psycopg2"])
                assert output["libpq"] >= 100000

    @pytest.mark.aws
    @pytest.mark.xfail
    def test_publish(self, build_dir, layer_cleanup):
        session = boto3.session.Session()

        layer_name = f"{STACKNAME}-TestLayer1"
        layer_description = "TestVersion1"
        published = publish_layer(
            session,
            layer_name,
            layer_description,
            DIR / "test_layer",
            build_dir,
            ["python3.7"],
            _permission_ids(session, None, None, True, False)[0],  # my account
        )

        assert published["Description"] == layer_description
        assert published["CompatibleRuntimes"] == ["python3.7"]

        # test local package.zip
        layer_zip = zipfile.ZipFile(build_dir / "package.zip")
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

        layers = list_layers(session, "python3.7")
        assert layer_names(layers) == [layer_name]

        layers = list_layers(session, "python3.8")
        assert layer_names(layers) == []

        versions = list(list_versions(session, layer_name))
        assert len(versions) == 1
        assert versions[0]["Description"] == layer_description

        versions = list(list_versions(session, layer_name, "python3.7"))
        assert len(versions) == 1
        assert versions[0]["Description"] == layer_description

        versions = list(list_versions(session, layer_name, "python3.8"))
        assert versions == []
