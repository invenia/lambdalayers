import argparse
import itertools
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import boto3

import plz


logger = logging.getLogger(__name__)


def list_layers(
    boto_session, runtime: Optional[str] = None
) -> Iterator[Dict[str, Any]]:
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


def publish_layer(
    boto_session,
    layer: str,
    version: str,
    local_path: Path,
    build_path: Path,
    runtimes: List[str],
    account: str,
    organization: Optional[str] = None,
) -> Dict[str, Any]:
    build_path = build_path or local_path / ".build"

    lambda_client = boto_session.client("lambda")

    files, requirements_file = _read_local_layer(local_path)
    package = plz.build_package(
        build_path,
        *files,
        requirements=requirements_file,
        zipped_prefix=Path("python"),
        force=True,
    )

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
        logger.info(f"Allowed organization '{organization}'' to access '{version_arn}'")
    elif account == "*":
        logger.info(f"Allowed anyone to access '{version_arn}'")
    else:
        logger.info(f"Allowed account '{account}' to access '{version_arn}'")

    return published


def main(args=None):
    args = parse_args(args=args)

    logging.basicConfig(level=args.log_level)
    logger.setLevel(args.log_level)

    session = boto3.session.Session(profile_name=args.profile, region_name=args.region)

    if session.region_name is None:
        logger.error(
            "No default region exists for your AWS profile. "
            "Please specify one manually by passing `--region REGION_NAME`."
        )
        exit(1)

    if args.command == "list":
        layers = list_layers(session, args.runtime)
        any_found = False

        for layer in layers:
            any_found = True
            print(layer)

        if not any_found:
            if args.runtime:
                logger.info(f"No layers found supporting '{args.runtime}'")
            else:
                logger.info(f"No layers found")
    elif args.command == "versions":
        versions = list_versions(session, args.layer, args.runtime)
        any_found = False

        for layer in versions:
            any_found = True
            print(layer)

        if not any_found:
            if args.runtime:
                logger.info(
                    f"No versions found for layer '{args.layer}' supporting '{args.runtime}"  # noqa: E501
                )
            else:
                logger.info(f"No versions found for layer '{args.layer}'")
    elif args.command == "publish":
        account, organization = _permission_ids(
            session,
            args.account,
            args.organization,
            args.my_account,
            args.my_organization,
        )

        print(
            publish_layer(
                session,
                args.layer,
                args.version,
                args.layer_path,
                None,
                args.runtimes,
                account,
                organization,
            )
        )


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Useful AWS Lambda layers for Invenia (and code to deploy them)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Subcommand help")
    subparsers.add_parser("list", help="List all available layers")
    subparsers.add_parser("versions", help="List all available versions of a layer")
    subparsers.add_parser("publish", help="Publish a new version of a layer")

    for name, subparser in subparsers.choices.items():
        subparser.add_argument(
            "--region",
            default=None,
            help=(
                "The AWS region to use."
                "If not given, deploy will fall back to config/env settings."
            ),
        )
        subparser.add_argument(
            "--profile",
            default=None,
            help=(
                "The AWS profile to use."
                "If not given, deploy will fall back to config/env settings."
            ),
        )

        logger_group_parent = subparser.add_argument_group(
            title="logging arguments",
            description="Control what log level the log outputs (default: logger.INFO)",
        )

        logger_group = logger_group_parent.add_mutually_exclusive_group()

        logger_group.add_argument(
            "-d",
            "--debug",
            dest="log_level",
            action="store_const",
            const=logging.DEBUG,
            default=logging.INFO,
            help="Set log level to DEBUG for more verbose output",
        )

        logger_group.add_argument(
            "-q",
            "--quiet",
            dest="log_level",
            action="store_const",
            const=logging.ERROR,
            default=logging.INFO,
            help="Suppress all logs except ERROR and CRITICAL",
        )

        if name == "publish":
            subparser.add_argument(
                "--layer-path", type=Path, help="Directory containing a layer"
            )

            subparser.add_argument(
                "--runtimes",
                nargs="+",
                required=True,
                help="Compatible runtimes (e.g., `python3.6 python3.7`) for this layer",
            )

            subparser.add_argument("--version", help="Layer version to publish")

            permissions_group_parent = subparser.add_argument_group(
                title="layer permissions",
                description="permissions for the resource-based policy of the layer",
            )

            permissions_group = permissions_group_parent.add_mutually_exclusive_group(
                required=True
            )

            permissions_group.add_argument(
                "--organization",
                default=None,
                help="Grant permissions to all accounts in this AWS Organization",
            )
            permissions_group.add_argument(
                "--my-organization",
                action="store_true",
                help="Grant permissions to all accounts in the AWS Organization of the current account",  # noqa: E501
            )
            permissions_group.add_argument(
                "--account",
                default=None,
                help="Grant permissions to a particular account, or specify open access with '*'",  # noqa: E501
            )
            permissions_group.add_argument(
                "--my-account",
                action="store_true",
                help="Grant permissions to the current account",
            )

        else:
            subparser.add_argument(
                "--runtime",
                default=None,
                help="Lambda runtime (e.g., `python3.7`) to filter by",
            )

        if name != "list":
            subparser.add_argument("--layer", help="Name of the layer")

    return parser.parse_args(args)


if __name__ == "__main__":
    main()
