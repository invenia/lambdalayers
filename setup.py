from os.path import abspath, dirname, join

from setuptools import find_packages, setup


TEST_DEPS = ["coverage", "pytest", "pytest-cov", "requests"]
CHECK_DEPS = ["isort", "flake8", "flake8-quotes", "pep8-naming", "black", "mypy"]
REQUIREMENTS = [
    "plz @ git+https://gitlab.invenia.ca/infrastructure/plz@master#egg=plz",
    "boto3",
]

EXTRAS = {"test": TEST_DEPS, "check": CHECK_DEPS, "dev": TEST_DEPS + CHECK_DEPS}

# Read in the version
with open(join(dirname(abspath(__file__)), "VERSION")) as version_file:
    version = version_file.read().strip()


setup(
    name="lambdalayers",
    version=version,
    description="Some useful AWS Lambda layers for Invenia (and code to deploy them)",
    author="Invenia Technical Computing",
    url="https://gitlab.invenia.ca/infrastructure/lambdalayers",
    packages=find_packages(exclude=["tests"]),
    install_requires=REQUIREMENTS,
    tests_require=TEST_DEPS,
    extras_require=EXTRAS,
    entry_points={"console_scripts": ["lls = lambdalayers.cli:main"]},
    include_package_data=True,
)
