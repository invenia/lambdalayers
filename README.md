# Lambda Layers

[![Docs Stable](https://img.shields.io/badge/docs-stable-blue.svg)](https://infrastructure.pages.invenia.ca/cloudspy/docs/)
[![Build Status](https://gitlab.invenia.ca/infrastructure/lambdalayers/badges/master/build.svg)](https://gitlab.invenia.ca/infrastructure/lambdalayers/commits/master)
[![Coverage Status](https://gitlab.invenia.ca/infrastructure/lambdalayers/badges/master/coverage.svg)](https://infrastructure.pages.invenia.ca/lambdalayers/coverage/)
[![Python Version](https://img.shields.io/badge/python-3.6-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

Some useful AWS Lambda layers for Invenia (and code to deploy them)

## Requirements

- python3.6+
- Should not be run in a virtualenv (like [plz](https://gitlab.invenia.ca/infrastructure/plz))

## Example

An example of publishing a layer:

```sh
lls publish --profile operations --layer pg8000 --version v0.0.8 --layer-path layers/pg8000/ --runtimes python3.7 --my-organization
```
