from importlib.machinery import SourceFileLoader
import os

from setuptools import find_packages, setup

lookout_core = SourceFileLoader("lookout", "./lookout/core/__init__.py").load_module()

with open(os.path.join(os.path.dirname(__file__), "README.md")) as f:
    long_description = f.read()

tests_require = ["docker>=3.4.0,<4.0"]
exclude_packages = ("lookout.core.tests",) \
    if not os.getenv("LOOKOUT_SDK_ML_SETUP_INCLUDE_TESTS", False) else ()

setup(
    name="lookout-sdk-ml",
    description="Lookout Python SDK for stateful source code analyzers, typically using "
                "Machine Learning.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    version=lookout_core.__version__,
    license="Apache-2.0",
    author="source{d}",
    author_email="machine-learning@sourced.tech",
    url="https://github.com/src-d/lookout-sdk-ml",
    download_url="https://github.com/src-d/lookout-sdk-ml",
    packages=find_packages(exclude=exclude_packages),
    namespace_packages=["lookout"],
    entry_points={
        "console_scripts": ["analyzer=lookout.__main__:main"],
    },
    keywords=["machine learning on source code", "babelfish", "lookout"],
    install_requires=[
        "bblfsh>=2.12.7,<3.0",
        "stringcase>=1.2.0,<2.0",
        "sqlalchemy>=1.0.0,<2.0",
        "sqlalchemy-utils>=0.33,<2.0",
        "pympler>=0.5,<2.0",
        "cachetools>=2.0,<3.0",
        "configargparse>=0.13,<2.0",
        "humanfriendly>=4.0,<5.0",
        "psycopg2-binary>=2.7,<3.0",
        "modelforge>=0.12.0,<0.13.0",
        "requirements-parser>=0.2.0,<2.0",
        "lookout-sdk>=0.4.1,<0.5",
        "packaging>=16.8,<20.0",
        "typing;python_version<'3.5'",
        "prometheus_client == 0.6.0",
    ],
    extras_require={
        "test": tests_require,
    },
    tests_require=tests_require,
    package_data={"": ["../license.md", "README.md", "../requirements.txt"],
                  "lookout.core": ["container/*", "examples/*.py"],
                  "lookout.core.tests": ["*.xz"],
                  },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Quality Assurance",
    ],
)
