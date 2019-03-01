## CLI

The Lambda Layers CLI (`lls`) provides the tools to publish new AWS Lambda layers, and query existing layers and layer versions.
For more information on layers, see the [official AWS Lambda Layers documentation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html).

### Usage

```eval_rst
.. runcmd:: python ./lambdalayers/cli.py --help
   :syntax: sh
   :prompt:
```

#### List Layers

```eval_rst
.. runcmd:: python ./lambdalayers/cli.py list --help
   :syntax: sh
   :prompt:
```

#### List Layer Versions

```eval_rst
.. runcmd:: python ./lambdalayers/cli.py versions --help
   :syntax: sh
   :prompt:
```

#### Publish a Layer Version

```eval_rst
.. runcmd:: python ./lambdalayers/cli.py publish --help
   :syntax: sh
   :prompt:
```
