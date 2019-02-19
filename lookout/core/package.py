import argparse
import importlib
import logging
import os
import shutil
import sys
from typing import Iterable, List, Tuple, Union

from clint.textui import prompt
import jinja2
from modelforge.environment import collect_loaded_packages
import requirements
import stringcase

from lookout.core import slogging


def package_cmdline_entry(args: argparse.Namespace) -> Union[None, int]:  # noqa: D401
    """
    Package several analyzers to a Docker container and write a sample Docker Compose config \
    for Lookout.

    :param args: Parsed command line arguments.
    :return: None or error code.
    """
    slogging.setup(args.log_level, False, args.log_config_path)
    return package(args.yes, args.no, args.workdir, args.analyzer, args.requirements,
                   args.repo, args.user, args.token)


def package(script_yes: bool, script_no: bool, wd: str, analyzers: Iterable[str],  # noqa: D401
            requirements_path: str, repo: str, user: str, token: str) -> Union[None, int]:  # noqa: D401,E501
    """
    Package several analyzers to a Docker container and write a sample Docker Compose config \
    for Lookout.

    :param script_yes: Force script execution in the end.
    :param script_no: Disable script execution in the end.
    :param wd: Working directory. All the files will be generated inside.
    :param analyzers: List of analyzer fully qualified module names.
    :param requirements_path: Path to requirements.txt. May be empty.
    :param repo: GitHub repo name to poll. E.g. "src-d/lookout".
    :param user: GitHub user name.
    :param token: GitHub user's token. Must have "repo" permissions. *not a password*
    :return: None or error code.
    """
    log = logging.getLogger("package")
    if script_yes and script_no:
        log.critical("Conflict between -y/--yes and -n/--no")
        return 1
    if os.path.exists(wd) and os.listdir(wd):
        log.critical("Not empty: %s", wd)
        return 2
    log.info("Preparing %s", wd)
    os.makedirs(wd, exist_ok=True)
    package_name = _process_analyzers(analyzers, wd, log)
    packages = _process_requirements(requirements_path, os.path.join(wd, "requirements.txt"), log)
    ndeps, ndeps_dev = _compose_native_deps(packages)
    _generate_configs(
        " ".join(analyzers), ndeps, ndeps_dev, package_name, wd, repo, user, token, log)
    script = "cd %s\ndocker build -t %s .\ndocker-compose up --force-recreate" % (wd, package_name)
    log.info("These are your next steps:\n\n%s\n", script)
    if script_yes or (not script_no and not prompt.yn("Run these commands now?", default="n")):
        os.execlp("sh",  "-x", "-c", script.replace("\n", " && "))


# The set of Python packages which are already installed in srcd/lookout-sdk-ml Docker image.
BUILT_IN_PKGS = {
    "args", "asdf", "bblfsh", "cachetools", "certifi", "chardet", "clint", "ConfigArgParse",
    "docker", "docker-pycreds", "dulwich", "google-api-core", "google-auth", "google-cloud-core",
    "google-cloud-storage", "google-resumable-media", "googleapis-common-protos", "grpcio",
    "grpcio-tools", "humanfriendly", "humanize", "idna", "Jinja2", "jsonschema", "lookout-sdk",
    "lookout-sdk-ml", "lz4", "MarkupSafe", "modelforge", "numpy", "pip", "protobuf",
    "psycopg2-binary", "pyasn1", "pyasn1-modules", "pygtrie", "Pympler", "python-dateutil",
    "pytz", "PyYAML", "requests", "rsa", "scipy", "semantic-version", "setuptools", "six",
    "SQLAlchemy", "SQLAlchemy-Utils", "stringcase", "urllib3", "websocket-client", "wheel",
    "requirements-parser", "xxhash",
}


# Ubuntu packages which are required to install specific Python packages.
# The first tuple contains the binary package names. They are installed into the container.
# The second tuple contains the development package names. They are intermediate and are
# installed temporarily for `pip install`.
NATIVE_DEPS = {
    "sourced-ml": (("libsnappy1v5",), ("libsnappy-dev",)),
    "Pillow-SIMD": (("zlib1g", "libjpeg-turbo8", "libpng16-16"),
                    ("zlib1g-dev", "libjpeg-turbo8-dev", "libpng-dev")),
    "python-igraph": (("libxml2", "zlib1g"), ("make", "libxml2-dev", "zlib1g-dev")),
}


def _process_analyzers(analyzers: Iterable[str], wd: str, log: logging.Logger) -> str:
    log.info("Importing %s", ", ".join(analyzers))
    anames = []
    sys.path.append(os.getcwd())
    copy_cwd = False
    for a in analyzers:
        cls = importlib.import_module(a).analyzer_class
        anames.append(stringcase.snakecase(cls.__name__.replace("Analyzer", "")))
        log.info("  %s@%s", cls.name, cls.version)
        if os.path.exists(a.replace(".", os.pathsep) + ".py"):
            copy_cwd = True
    if copy_cwd:
        shutil.rmtree(wd, ignore_errors=True)
        shutil.copytree(os.getcwd(), wd)
    sys.path = sys.path[:-1]
    package_name = "_".join(sorted(anames))
    return package_name


def _process_requirements(src_path: str, dest_path: str, log: logging.Logger) -> List[str]:
    if not src_path:
        log.info("Looking for Python dependencies")
        packages = []
        for pkg, ver in sorted(collect_loaded_packages()):
            if pkg in BUILT_IN_PKGS:
                log.debug("%s already exists in the base image, skipped", pkg)
                continue
            if "dev" in ver:
                log.warning("%s==%s may be built locally, skipped", pkg, ver)
                continue
            packages.append((pkg, ver))
        log.info("Writing requirements.txt")
        with open(dest_path, "w") as fout:
            fout.writelines("%s==%s\n" % p for p in packages)
    else:
        shutil.copy(src_path, dest_path)
    with open(dest_path) as fin:
        return [req.name for req in requirements.parse(fin.read())]


def _compose_native_deps(packages: Iterable[str]) -> Tuple[str, str]:
    pkgs = set()
    pkgs_dev = set()
    for pkg in packages:
        deps, deps_dev = NATIVE_DEPS.get(pkg, ((), ()))
        pkgs.update(deps)
        pkgs_dev.update(deps_dev)
    return " ".join(sorted(pkgs)), " ".join(sorted(pkgs_dev))


def _generate_configs(analyzers: str, ndeps: str, ndeps_dev: str, package_name: str, wd: str,
                      repo: str, user: str, token: str, log: logging.Logger) -> None:
    jenv = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    cpath = os.path.join(os.path.dirname(__file__), "container")
    loader = jinja2.FileSystemLoader((cpath,), followlinks=True)

    def copy(filename):
        shutil.copy(os.path.join(cpath, filename), os.path.join(wd, filename))

    log.info("Generating Dockerfile")
    template = loader.load(jenv, "Dockerfile.jinja2")
    with open(os.path.join(wd, "Dockerfile"), "w") as fout:
        fout.write(template.render(analyzers=analyzers, package_name=package_name,
                                   pkg=ndeps, pkg_dev=ndeps_dev))
    copy("analyzers.yml")
    log.info("Generating lookout.yml")
    template = loader.load(jenv, "lookout.yml.jinja2")
    with open(os.path.join(wd, "lookout.yml"), "w") as fout:
        fout.write(template.render(
            analyzers=analyzers, package_name=package_name, repo=repo,
            github_user=user, github_token=token))
    log.info("Generating docker-compose.yml")
    copy("wait-for-port.sh")
    copy("wait-for-postgres.sh")
    template = loader.load(jenv, "docker-compose.yml.jinja2")
    with open(os.path.join(wd, "docker-compose.yml"), "w") as fout:
        fout.write(template.render(
            analyzers=analyzers, package_name=package_name))
