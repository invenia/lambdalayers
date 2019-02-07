from setuptools import find_packages, setup

from lambdalayers.version import __version__

TEST_DEPS = ["coverage", "pytest", "pytest-cov"]
CHECK_DEPS = ["isort", "flake8", "flake8-quotes", "pep8-naming", "black", "mypy"]
REQUIREMENTS = ["plz", "boto3"]

EXTRAS = {"test": TEST_DEPS, "check": CHECK_DEPS, "dev": TEST_DEPS + CHECK_DEPS}

setup(
    name="Lambda Layers",
    version=__version__,
    description="Some useful AWS Lambda layers for Invenia (and code to deploy them)",
    author="Invenia Technical Computing",
    url="https://gitlab.invenia.ca/infrastructure/lambdalayers",
    packages=find_packages(exclude=["tests"]),
    dependency_links=["git+https://gitlab.invenia.ca/infrastructure/plz@pip-fix"],
    install_requires=REQUIREMENTS,
    tests_require=TEST_DEPS,
    extras_require=EXTRAS,
    entry_points={"console_scripts": ["lls = lambdalayers.cli:main"]},
)
