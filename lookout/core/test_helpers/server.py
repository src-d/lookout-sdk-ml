"""Utils to work with lookout-sdk binary."""
import io
import logging
import os
import pathlib
import random
from shutil import copyfileobj
import socket
import subprocess
import sys
import tarfile
import tempfile
from urllib.error import HTTPError
from urllib.request import urlopen

from lookout.core.api.version import __version__ as binver


exefile = pathlib.Path(tempfile.gettempdir()) / "lookout-sdk-ml-tests" / "server"


def fetch():
    """
    Fetch corresponding lookout-sdk executable.
    """
    log = logging.getLogger("fetch")
    exefile.parent.mkdir(exist_ok=True)
    try:
        buffer = io.BytesIO()
        with urlopen("https://github.com/src-d/lookout/releases/download/"
                     "%s/lookout-sdk_%s_%s_amd64.tar.gz" % (binver, binver, sys.platform)
                     ) as response:
            copyfileobj(response, buffer)
        buffer.seek(0)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            with exefile.open("wb") as fout:
                copyfileobj(tar.extractfile("lookout-sdk_%s_amd64/lookout-sdk" % sys.platform),
                            fout)
        os.chmod(str(exefile), 0o775)
    except HTTPError as e:
        if e.code == 404:
            log.error("Release %s for %s platform is missing." % (binver, sys.platform))
        raise e from None
    except Exception as e:
        if exefile.exists():
            os.remove(str(exefile))
        raise e from None


def run(cmd: str, fr: str, to: str, port: int, git_dir: str=".",
        log_level: str="info", config_json: str=None) -> subprocess.CompletedProcess:
    """
    Run lookout-sdk executable. If you do not have it please fetch first.

    :param cmd: Sub-command to run.
    :param fr: Corresponds to --from flag.
    :param to: Corresponds to --to flag.
    :param port: Running analyzer port on localhost.
    :param git_dir: Corresponds to --git-dir flag.
    :param log_level: Corresponds to --log-level flag.
    :param config_json: Corresponds to --config-json flag.
    :return: CompletedProcess with return code.
    """
    command = [
        str(exefile), cmd, "ipv4://localhost:%d" % port,
        "--from", fr,
        "--to", to,
        "--git-dir", git_dir,
        "--log-level", log_level,
    ]
    if config_json:
        command.extend(("--config-json", config_json))
    return subprocess.run(command, stdout=sys.stdout, stderr=sys.stderr, check=True)


def find_port(attempts: int = 100) -> int:
    """
    Find available port on localhost.

    :param attempts: Attempts number.
    :return: Founded port number.
    """
    while True:
        attempts -= 1
        if attempts == 0:
            raise ConnectionError("cannot find an open port")
        port = random.randint(1024, 32768)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("localhost", port))
        except ConnectionRefusedError:
            return port
        finally:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()
