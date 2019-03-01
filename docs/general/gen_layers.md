## Provided Layers

There are a few published layers which are located in this repository.
They have been published to the Operations account (468665244580) and are available to any account in the Invenia organization.
They are located in the `layers` folder.

### cfnresponse

This layer is based on the Python 3 code located in the [CloudFormation Lambda documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-lambda-function-code.html).
It has been modified for formatting only.
It has been published for Python 3.6 and Python 3.7 runtimes.

### pg8000

This layer consists solely of a `requirements.txt` file which installs [pg8000](https://github.com/tlocke/pg8000) and its dependencies.
`pg8000` is a pure-Python [PostgreSQL](https://www.postgresql.org/) client.
It has been published with separate versions for Python 3.6 and Python 3.7.
