# lookout-sdk-ml

Lookout Python SDK for stateful analyzers, typically using Machine Learning.

[![Read the Docs](https://img.shields.io/readthedocs/lookout-sdk-ml.svg)](https://readthedocs.org/projects/lookout-sdk-ml/)
[![Travis build status](https://travis-ci.org/src-d/lookout-sdk-ml.svg?branch=master)](https://travis-ci.org/src-d/lookout-sdk-ml)
[![Code coverage](https://codecov.io/github/src-d/lookout-sdk-ml/coverage.svg)](https://codecov.io/github/src-d/lookout-sdk-ml)
[![Docker build status](https://img.shields.io/docker/build/srcd/lookout-sdk-ml.svg)](https://hub.docker.com/r/srcd/lookout-sdk-ml)
[![PyPi package status](https://img.shields.io/pypi/v/lookout-sdk-ml.svg)](https://pypi.python.org/pypi/lookout-sdk-ml)
![stability: beta](https://svg-badge.appspot.com/badge/stability/beta?color=ff8000)
[![Apache 2.0 license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

[Overview](#overview) • [Installation](#installation) • [How To Use](#how-to-use) • [Contributions](#contributions) • [License](#license)


## Overview

This is a Python package which provides API to create stateful analyzers for
the [Lookout framework](https://github.com/src-d/lookout).
"Stateful" means that such analyzers update "state" after each push to repository. In machine
learning terms, a state is a model and updating state is training.
Thus all the Lookout analyzers which use machine learning are based on this API.

You benefit from `lookout-sdk-ml` if you:

- Code in Python.
- Want to create a stateful analyzer for Lookout.
- Find the [lookout-sdk](https://github.com/src-d/lookout-sdk) too low level.


## Installation

You need Python 3.5 or later.

```
pip3 install lookout-sdk-ml
```

## How To Use

Please refer to the [getting started guide](lookout/core/doc/getting_started.md).

## Contributions

Contributions are very welcome and desired! Please follow the [code of conduct](doc/code_of_conduct.md)
and read the [contribution guidelines](doc/contributing.md).

## License

Apache-2.0, see [license.md](license.md).
