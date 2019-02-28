## Lambda Layer Concepts

This documentation assumes you are already familiar with [Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html) functions and basic [CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/Welcome.html) usage.

For further information on Lambda layers see the [official AWS documentation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html).

### Layers

A layer is a way to share code dependencies between Lambda functions.
Layers are stored as ZIP files which are unpacked into Lambda function environments under `/opt`.
Layers can contain any files, but there are [specific paths](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html#configuration-layers-path) to use for different Lambda runtimes.
This package currently only handles Python 3 runtimes, so all packages are located in a `python` directory which gets extracted to `/opt/python`.
This path is automatically in the Lambda's `PYTHONPATH`.

Since Lambdas can only use up to 10 layers, it is recommended that packages be grouped into layers when they are only used together.

### Layer Versions

A layer is a named entity in AWS, but the code exists in a layer version.
Layer versions have their own ARN, and are assigned a unique integer version identifier, in addition to a user-provided description.
It is recommended that the description be a [semver](https://semver.org/) version, e.g., `v1.0.1`.
Layer versions cannot be replaced, only deleted, and continue to exist after deletion until any currently-running Lambda functions finish.

It is the layer version, not the layer, which is added to a Lambda function.

### Layer Directory Structure

The structure described below is a convention used by this package, and is not a fundamental property of Lambda layers.

A layer directory can contain files and folders, which will be copied straight into the ZIP file.
Any top-level files or folders which begin with `.` will be ignored.
The directory can also contain a `requirements.txt` file, which will not be copied into the ZIP file.
Instead, the packages listed there are installed and copied in.

Two example layers are located in the [`layers` directory](https://gitlab.invenia.ca/infrastructure/lambdalayers/tree/master/layers) of this repository.

### Layer Version Permissions

Layer versions have an associated policy that permits usage by Lambda functions.
Individual permissions [can be added](https://docs.aws.amazon.com/lambda/latest/dg/API_AddLayerVersionPermission.html) to allow access by single accounts, all accounts in an [AWS Organization](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_introduction.html), or all AWS accounts (i.e., public).
It's possible to add several permissions to one layer version, but this package only supports adding one layer version permission, and only when publishing the layer version.

It is recommended that access be provided to the caller's account (for testing only), or to the whole Invenia organization for use by Lambda functions.
The `lls` CLI [provides](./gen_cli.html#publish-a-layer-version) the arguments `--my-account` and `--my-organization` for this purpose.
Layers are typically published in the `operations` account, so the publishing user should either assume a role in that account prior to publishing or use the `--profile` argument.
