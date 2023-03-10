import itertools
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from zipfile import ZipFile

import plz  # type: ignore


RUNTIME_VERSION_REGEX = r"^python(?P<version>\d\.\d+)$"


logger = logging.getLogger(__name__)


def list_layers(
    boto_session, runtime: Optional[str] = None
) -> Iterator[Dict[str, Any]]:
    """List Lambda layers visible from the current AWS account

    Args:
        boto_session: A boto3.session.Session instance
        runtime (optional): Only fetch layers which support this runtime

    Returns:
        An iterator over dicts with str keys, each representing a Lambda layer

        An example dict::

            {
                'LayerName': 'cfnresponse',
                'LayerArn':
                    'arn:aws:lambda:us-east-1:468665244580:layer:cfnresponse',
                'LatestMatchingVersion': {
                    'LayerVersionArn':
                        'arn:aws:lambda:us-east-1:468665244580:layer:cfnresponse:2',
                    'Version': 2,
                    'Description': 'v0.0.2',
                    'CreatedDate': '2019-02-08T21:44:43.782+0000',
                    'CompatibleRuntimes': ['python3.6'],
                },
            }
    """
    lambda_client = boto_session.client("lambda")
    paginator = lambda_client.get_paginator("list_layers")
    if runtime:
        paginated = paginator.paginate(CompatibleRuntime=runtime)
    else:
        paginated = paginator.paginate()
    layer_pages = map(lambda page: page["Layers"], paginated)
    layers = itertools.chain.from_iterable(layer_pages)

    return layers


def list_versions(
    boto_session, layer: str, runtime: Optional[str] = None
) -> Iterator[Dict[str, Any]]:
    """List versions of a Lambda layer visible from the current AWS account

    Args:
        boto_session: A boto3.session.Session instance
        layer: Layer name or ARN
        runtime (optional): Only fetch layer versions which support this runtime

    Returns:
        An iterator over dicts with str keys, each representing a Lambda layer version

        An example dict::

            {
                'LayerVersionArn':
                    'arn:aws:lambda:us-east-1:468665244580:layer:cfnresponse:2',
                'Version': 2,
                'Description': 'v0.0.2',
                'CreatedDate': '2019-02-08T21:44:43.782+0000',
                'CompatibleRuntimes': ['python3.6'],
            }
    """
    lambda_client = boto_session.client("lambda")
    paginator = lambda_client.get_paginator("list_layer_versions")
    if runtime:
        paginated = paginator.paginate(LayerName=layer, CompatibleRuntime=runtime)
    else:
        paginated = paginator.paginate(LayerName=layer)
    layer_pages = map(lambda page: page["LayerVersions"], paginated)
    layers = itertools.chain.from_iterable(layer_pages)

    return layers


def _read_local_layer(local_path: Path) -> Tuple[List[Path], Optional[Path]]:
    layer_files = list(filter(lambda path: not path.match(".*"), local_path.glob("*")))

    requirements_file: Optional[Path] = local_path / "requirements.txt"
    if requirements_file in layer_files:
        layer_files.remove(requirements_file)
    else:
        requirements_file = None

    return layer_files, requirements_file


def _permission_ids(
    boto_session,
    account: Optional[str],
    organization: Optional[str],
    my_account: bool,
    my_organization: bool,
) -> Tuple[str, Optional[str]]:
    if my_organization:
        org_client = boto_session.client("organizations")
        organization = org_client.describe_organization()["Organization"]["Id"]
    elif my_account:
        sts_client = boto_session.client("sts")
        account = sts_client.get_caller_identity()["Account"]

    if organization:
        account = "*"

    if not account:
        raise ValueError("`account` or `organization` must be specified")

    return account, organization


def _zipfiles_equal(z1: Path, z2: Path):
    z1_files = sorted(ZipFile(z1).infolist(), key=lambda x: x.filename)
    z2_files = sorted(ZipFile(z2).infolist(), key=lambda x: x.filename)

    def zipinfo_equal(a, b):
        if a is None or b is None:
            return False

        return (
            a.filename == b.filename and a.file_size == b.file_size and a.CRC == b.CRC
        )

    return all(
        itertools.starmap(zipinfo_equal, itertools.zip_longest(z1_files, z2_files))
    )


def python_version(runtime: str):
    m = re.match(RUNTIME_VERSION_REGEX, runtime)
    if m is None:
        raise ValueError(
            f"Runtime '{runtime}' invalid; must match `{RUNTIME_VERSION_REGEX}`"
        )

    return m.group("version")


def build_layer(
    local_path: Path, runtimes: List[str], build_path: Optional[Path] = None
):
    if not runtimes:
        raise ValueError("Must build for at least one Lambda runtime")

    build_path = build_path or local_path / ".build"

    package_zips = []
    for version in map(python_version, runtimes):
        version_build_path = build_path / version
        files, requirements_file = _read_local_layer(local_path)
        package_zips.append(
            plz.build_zip(
                version_build_path,
                *files,
                requirements=requirements_file,
                python_version=version,
                zipped_prefix=Path("python"),
            )
        )

    if len(runtimes) == 1:
        logger.debug("Built a single-runtime layer zip")
        return Path(shutil.copy(package_zips[0], build_path))

    # if the zip files are all the same, we don't need to create a multiversion zip
    if all(map((lambda p: _zipfiles_equal(package_zips[0], p)), package_zips[1:])):
        logger.debug("Built a cross-compatible layer zip")
        return Path(shutil.copy(package_zips[0], build_path))

    multi_path = build_path / package_zips[0].name
    with tempfile.TemporaryDirectory(prefix="lambdalayers") as tmp_dir:
        tmp_path = Path(tmp_dir)
        combine_path = tmp_path / "package"

        # writing data from Python into a zip file with zipfile does not preserve
        # permissions, so here we extract each zip to disk and recombine them
        for package, runtime in zip(package_zips, runtimes):
            extract_path = tmp_path / runtime
            extract_path.mkdir()
            prefix = Path("python") / "lib" / runtime / "site-packages"

            with ZipFile(package, "r") as single_z:
                single_z.extractall(path=extract_path)

            os.renames(extract_path / "python", combine_path / prefix)

        shutil.make_archive(build_path / package_zips[0].stem, "zip", combine_path)

    logger.debug("Built a multi-runtime layer zip")
    return multi_path


def publish_layer(
    boto_session,
    layer: str,
    version: str,
    local_path: Path,
    build_path: Optional[Path],
    runtimes: List[str],
    account: str,
    organization: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish a Lambda layer

    Args:
        boto_session: A boto3.session.Session instance
        layer: The name for the layer
        version: The description for the layer version
        local_path: The location of the files for the layer version
        build_path: The location for the temporary build directory, or None
        runtimes: List of runtimes the layer version supports
        account: The account id for the account allowed to access this layer
            version, or '*'
        organization (optional): The organization id for the organization
            allowed to access this layer (if this is provided, account should
            be '*')

    Returns:
        A dict with str keys, representing the published Lambda layer version

        An example dict::

            {
                'ResponseMetadata': {
                    'RequestId': '88917c99-3ba1-11e9-843c-57b89af855ed',
                    'HTTPStatusCode': 201,
                    'HTTPHeaders': {
                        'date': 'Thu, 28 Feb 2019 21:41:01 GMT',
                        'content-type': 'application/json',
                        'content-length': '1566',
                        'connection': 'keep-alive',
                        'x-amzn-requestid':
                            '88917c99-3ba1-11e9-843c-57b89af855ed',
                    },
                    'RetryAttempts': 0,
                },
                'Content': {
                    'Location': (
                        'https://prod-04-2014-layers.s3.amazonaws.com/snapshot'
                        's/468665244580/cfnresponse-31b1a38e-3e67-4742-94c3-b3'
                        '03c005cbc0?versionId=kVpRDTcxaNWGwwoSm9411v7EWIcDvrTU'
                        '&X-Amz-Security-Token=FQoGZXIvYXdzEO7%2F%2F%2F%2F%2F%'
                        '2F%2F%2F%2F%2FwEaDAQpqftoIR%2B7Z6NQAyK3A22UzG8sgM3N8p'
                        'nGx%2BSeMB8ytJmvlcl9olglEXlCOiBNTA8riLM%2FqDu0iu12mwT'
                        'ar0Dp5ZH1vZm3N270ULFhk%2FcTqUhsTKZ8vAFlQN6Aiw5IAkB1nZ'
                        'dDP6AKS6h8HbCYUCad6EV%2FeD0XZy97u7POBzkVoW6PeRtR3P6m4'
                        'zGMbwDAlZQwCA3UrXGa1nDvbaz01rszAIlIIJ4VOX%2FsoJKYxJci'
                        'VM1E5D2BE8L4jgXfNVNedxAPzlUtcvXuAP%2BGZt6FDbOgNP%2F6s'
                        'mV85RYKNH1cyJUHX6oLTt0HZIy0L2MqVVElBHNPreXv1CsWZyAxRp'
                        '7eSaYdnvERhKe%2BfyTZYuDmrzRG%2BcsAWTSA9FbceNOQ%2Br3BC'
                        'kmWDmAVcaAIz3IVLWRnoNC%2BJVunqGjn3i%2FfZknE9uZT7kkqGd'
                        'bpeAPgbEIHv07ikzJlIfj2CqePnkktn7A24tgrlpC0PhNSP2a2%2B'
                        'QGWLZXIfVJCqt5UyXyEJAH%2FvlaFbV%2BdfkRM%2FmtVhStxOjob'
                        'u9fkceqOLC%2BQbLhPsj8zuLC3mrt%2BAmYZ%2BbpzYxtqym2qjEl'
                        'm8e%2FEyF1hGqRjGV0PESRLXk%2FzDiQotYfh4wU%3D&X-Amz-Alg'
                        'orithm=AWS4-HMAC-SHA256&X-Amz-Date=20190228T214057Z&X'
                        '-Amz-SignedHeaders=host&X-Amz-Expires=600&X-Amz-Crede'
                        'ntial=ASIA25DCYHY3SG446V37%2F20190228%2Fus-east-1%2Fs'
                        '3%2Faws4_request&X-Amz-Signature=f1ebc2a55fb3b2bc3fd1'
                        '2645986ee015f94f2a5bb72b5e19b73399ebba49e285'
                    ),
                    'CodeSha256':
                        'YWAl3bA2336oE9UeBBHzkK02QBKGxiPkT6JmNY8AA4A=',
                    'CodeSize': 1991,
                },
                'LayerArn':
                    'arn:aws:lambda:us-east-1:468665244580:layer:cfnresponse',
                'LayerVersionArn':
                    'arn:aws:lambda:us-east-1:468665244580:layer:cfnresponse:3',
                'Description': 'v0.0.3',
                'CreatedDate': '2019-02-28T21:41:01.191+0000',
                'Version': 3,
                'CompatibleRuntimes': ['python3.6'],
            }

        Note that the 'Location' value is a temporary URL valid for 10 minutes
    """
    lambda_client = boto_session.client("lambda")

    package = build_layer(local_path, runtimes, build_path)

    logger.info(f"Built package for {layer} at {package}")

    published = lambda_client.publish_layer_version(
        LayerName=layer,
        Description=version,
        Content={"ZipFile": package.read_bytes()},
        CompatibleRuntimes=runtimes,
    )

    version_arn = published["LayerVersionArn"]

    logger.info(f"Published version '{version}' of layer '{layer}' at '{version_arn}'")

    permission_statement = lambda_client.add_layer_version_permission(  # noqa: F841
        LayerName=published["LayerArn"],
        VersionNumber=published["Version"],
        Action="lambda:GetLayerVersion",
        StatementId="LayerVersionPermission",
        Principal=account,
        **({"OrganizationId": organization} if organization else {}),
    )

    if organization:
        logger.info(f"Allowed organization '{organization}' to access '{version_arn}'")
    elif account == "*":
        logger.info(f"Allowed anyone to access '{version_arn}'")
    else:
        logger.info(f"Allowed account '{account}' to access '{version_arn}'")

    return published
