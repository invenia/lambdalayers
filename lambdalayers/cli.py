import argparse
import logging
from pathlib import Path

import boto3

from lambdalayers import api


logger = api.logger


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
        layers = api.list_layers(session, args.runtime)
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
        versions = api.list_versions(session, args.layer, args.runtime)
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
        account, organization = api._permission_ids(
            session,
            args.account,
            args.organization,
            args.my_account,
            args.my_organization,
        )

        print(
            api.publish_layer(
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
                "The AWS region to use. "
                "If not given, deploy will fall back to config/env settings."
            ),
        )
        subparser.add_argument(
            "--profile",
            default=None,
            help=(
                "The AWS profile to use. "
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
                help=(
                    "Compatible runtimes (e.g., `python3.6 python3.7`) for this layer. "
                    "Due to limitations with the `plz` library, only provide the "
                    "current version of python for layers with requirements."
                ),
            )

            subparser.add_argument(
                "--version", default="", help="Layer version to publish"
            )

            permissions_group_parent = subparser.add_argument_group(
                title="layer permissions",
                description=(
                    "Permissions for the resource-based policy of the layer. "
                    "Provide one of the following arguments:"
                ),
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
