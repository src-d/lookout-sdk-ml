"""Utils to work with lookout-sdk binary."""
import io
import json
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
from typing import Optional
from urllib.error import HTTPError
from urllib.request import urlopen

from lookout.core.api.version import __version__ as binver


class LookoutSDK:
    """
    Wrapper class for `lookout-sdk` executable.

    Allows you to query analyzers the same way lookout server do.
    About lookout-sdk read https://github.com/src-d/lookout-sdk
    """

    _log = logging.getLogger("LookoutSDK")

    def __init__(self):
        """
        Fetch lookout-sdk executable if it is missing.
        """
        self._version = binver
        self._exefile = (pathlib.Path(tempfile.gettempdir()) /
                         "lookout-sdk-ml" / ("lookout-sdk-%s" % self._version))
        if not self._exefile.exists():
            self.fetch()

    version = property(lambda self: self._version)

    def fetch(self):
        """
        Download the lookout-sdk executable from GitHub Releases.
        """
        self._exefile.parent.mkdir(exist_ok=True)
        platform = sys.platform
        try:
            buffer = io.BytesIO()
            with urlopen("https://github.com/src-d/lookout/releases/download/"
                         "%s/lookout-sdk_%s_%s_amd64.tar.gz" % (binver, binver, platform),
                         ) as response:
                copyfileobj(response, buffer)
            buffer.seek(0)
            with tarfile.open(fileobj=buffer, mode="r:gz") as tar, \
                    self._exefile.open("wb") as fout:
                copyfileobj(tar.extractfile("lookout-sdk_%s_amd64/lookout-sdk" % platform), fout)
            os.chmod(str(self._exefile), 0o775)
        except HTTPError as e:
            if e.code == 404:
                self._log.error("Release %s for %s platform is missing." % (binver, platform))
            raise e from None
        except Exception as e:
            if self._exefile.exists():
                os.remove(str(self._exefile))
            raise e from None

    def push(self, fr: str, to: str, port: int, *, git_dir: str, bblfsh: Optional[str]=None,
             log_level: Optional[str]=None, config_json: Optional[dict]=None) \
            -> subprocess.CompletedProcess:
        """
        Provide a simple data server and triggers an analyzer push event.

        :param fr: Corresponds to --from flag.
        :param to: Corresponds to --to flag.
        :param port: Running analyzer port on localhost.
        :param git_dir: Corresponds to --git-dir flag.
        :param log_level: Corresponds to --log-level flag.
        :param bblfsh: Corresponds to --bblfshd flag.
        :param config_json: Corresponds to --config-json flag.
        :return: CompletedProcess with return code.
        """
        return self._run("push", fr, to, port, git_dir, bblfsh, log_level, config_json)

    def review(self, fr: str, to: str, port: int, *, git_dir: str, bblfsh: Optional[str]=None,
               log_level: Optional[str]=None, config_json: Optional[dict]=None) \
            -> subprocess.CompletedProcess:
        """
        Provide a simple data server and triggers an analyzer review event.

        :param fr: Corresponds to --from flag.
        :param to: Corresponds to --to flag.
        :param port: Running analyzer port on localhost.
        :param git_dir: Corresponds to --git-dir flag.
        :param log_level: Corresponds to --log-level flag.
        :param bblfsh: Corresponds to --bblfshd flag.
        :param config_json: Corresponds to --config-json flag.
        :return: CompletedProcess with return code.
        """
        return self._run("review", fr, to, port, git_dir, bblfsh, log_level, config_json)

    def _run(self, cmd: str, fr: str, to: str, port: int, git_dir: str, bblfsh: Optional[str],
             log_level: Optional[str], config_json: Optional[dict]) -> subprocess.CompletedProcess:
        """
        Run lookout-sdk executable. If you do not have it please fetch first.

        :param cmd: Sub-command to run.
        :param fr: Corresponds to --from flag.
        :param to: Corresponds to --to flag.
        :param port: Running analyzer port on localhost.
        :param git_dir: Corresponds to --git-dir flag.
        :param log_level: Corresponds to --log-level flag.
        :param bblfsh: Corresponds to --bblfshd flag.
        :param config_json: Corresponds to --config-json flag.
        :return: CompletedProcess with return code.
        """
        command = [
            str(self._exefile), cmd, "ipv4://localhost:%d" % port,
            "--from", fr,
            "--to", to,
            "--git-dir", git_dir,
        ]
        if log_level:
            command.extend(("--log-level", log_level))
        if bblfsh:
            command.extend(("--bblfshd", "ipv4://" + bblfsh))
        if config_json:
            command.extend(("--config-json", json.dumps(config_json)))
        return subprocess.run(command, stdout=sys.stdout, stderr=sys.stderr, check=True)


def check_port_free(port: int) -> bool:
    """
    Check if the port is not taken on localhost.

    :param port: Port number.
    :return: True if available else False.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("localhost", port))
        return False
    except ConnectionRefusedError:
        return True
    finally:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        s.close()


def find_port(attempts: int = 100) -> int:
    """
    Find a free port on localhost.

    :param attempts: Number of random search attempts.
    :return: Found free port number.
    """
    while True:
        attempts -= 1
        if attempts == 0:
            raise ConnectionError("cannot find an open port")
        port = random.randint(1024, 32768)
        if check_port_free(port):
            return port
