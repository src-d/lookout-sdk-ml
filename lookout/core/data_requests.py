import functools
import logging
import os
import threading
from typing import Iterable, Optional, Tuple

import bblfsh
import grpc

from lookout.core.analyzer import Analyzer, AnalyzerModel, ReferencePointer
from lookout.core.api.service_analyzer_pb2 import Comment
from lookout.core.api.service_data_pb2 import Change, ChangesRequest, File, FilesRequest
from lookout.core.api.service_data_pb2_grpc import DataStub
from lookout.core.garbage_exclusion import GARBAGE_PATTERN
from lookout.core.ports import Type


class DataService:
    """
    Retrieves UASTs/files from the Lookout server.
    """

    GRPC_MAX_MESSAGE_SIZE = 100 * 1024 * 1024
    _log = logging.getLogger("DataService")

    def __init__(self, address: str):
        """
        Initialize a new instance of DataService.

        :param address: GRPC endpoint to use.
        """
        self._data_request_local = threading.local()
        self._data_request_channels = []
        self._data_request_address = address

    def __str__(self):
        """Summarize the DataService instance as a string."""
        return "DataService(%s)" % self._data_request_address

    def get_data(self) -> DataStub:
        """
        Return a `DataStub` for the current thread.
        """
        stub = getattr(self._data_request_local, "data_stub", None)
        if stub is None:
            self._data_request_local.data_stub = stub = DataStub(self._get_channel())
        return stub

    def get_bblfsh(self) -> bblfsh.aliases.ProtocolServiceStub:
        """
        Return a Babelfish `ProtocolServiceStub` for the current thread.
        """
        stub = getattr(self._data_request_local, "bblfsh_stub", None)
        if stub is None:
            self._data_request_local.bblfsh_stub = stub = \
                bblfsh.aliases.ProtocolServiceStub(self._get_channel())
        return stub

    def shutdown(self):
        """
        Close all the open network connections.
        """
        self._log.info("Shutting down")
        for channel in self._data_request_channels:
            channel.close()
        self._data_request_channels.clear()
        self._data_request_local = threading.local()

    def close_channel(self):
        """
        Close the current channel and free all the associated resources.
        """
        channel = getattr(self._data_request_local, "channel", None)
        if channel is not None:
            self._data_request_channels.remove(channel)
            self._data_request_local.channel = None
            self._data_request_local.data_stub = None
            self._data_request_local.bblfsh_stub = None
            channel.close()
            self._log.info("Disposed %s", channel)

    def _get_channel(self) -> grpc.Channel:
        channel = getattr(self._data_request_local, "channel", None)
        if channel is None:
            self._data_request_local.channel = channel = grpc.insecure_channel(
                self._data_request_address,
                options=[
                    ("grpc.max_send_message_length", self.GRPC_MAX_MESSAGE_SIZE),
                    ("grpc.max_receive_message_length", self.GRPC_MAX_MESSAGE_SIZE),
                ])
            self._data_request_channels.append(channel)
            self._log.info("Opened %s", channel)
        return channel


def _handle_rpc_errors(func):
    @functools.wraps(func)
    def wrapped_handle_rpc_errors(cls: Type[Analyzer], ptr: ReferencePointer, config: dict,
                                  data_service: DataService, **data) -> AnalyzerModel:
        try:
            return func(cls, ptr, config, data_service, **data)
        except grpc.RpcError as e:
            data_service.close_channel()
            raise e from None

    return wrapped_handle_rpc_errors


def with_changed_uasts(func):  # noqa: D401
    """
    Decorator to provide "changes" keyword argument to `**data` in `Analyzer.analyze()`.

    "changes" contain the list of `Change` - see lookout/core/server/sdk/service_data.proto.
    The changes will have only UASTs, no raw file contents.

    :param func: Method with the signature compatible with `Analyzer.analyze()`.
    :return: The decorated method.
    """
    @functools.wraps(func)
    @_handle_rpc_errors
    def wrapped_with_changed_uasts(
            self: Analyzer, ptr_from: ReferencePointer, ptr_to: ReferencePointer,
            data_service: DataService, **data) -> [Comment]:
        changes = request_changes(
            data_service.get_data(), ptr_from, ptr_to, contents=False, uast=True)
        return func(self, ptr_from, ptr_to, data_service, changes=changes, **data)

    return wrapped_with_changed_uasts


def with_changed_uasts_and_contents(func):  # noqa: D401
    """
    Decorator to provide "changes" keyword argument to `**data` in `Analyzer.analyze()`.

    "changes" contain the list of `Change` - see lookout/core/server/sdk/service_data.proto.
    The changes will have both UASTs and raw file contents.

    :param func: Method with the signature compatible with `Analyzer.analyze()`.
    :return: The decorated method.
    """
    @functools.wraps(func)
    @_handle_rpc_errors
    def wrapped_with_changed_uasts_and_contents(
            self: Analyzer, ptr_from: ReferencePointer, ptr_to: ReferencePointer,
            data_service: DataService, **data) -> [Comment]:
        changes = request_changes(
            data_service.get_data(), ptr_from, ptr_to, contents=True, uast=True)
        return func(self, ptr_from, ptr_to, data_service, changes=changes, **data)

    return wrapped_with_changed_uasts_and_contents


def with_uasts(func):  # noqa: D401
    """
    Decorator to provide "files" keyword argument to `**data` in `Analyzer.train()`.

    "files" are the list of `File`-s with all the UASTs for the passed Git repository URL and
    revision, see lookout/core/server/sdk/service_data.proto.

    :param func: Method with the signature compatible with `Analyzer.train()`.
    :return: The decorated method.
    """
    @functools.wraps(func)
    @_handle_rpc_errors
    def wrapped_with_uasts(cls: Type[Analyzer], ptr: ReferencePointer, config: dict,
                           data_service: DataService, **data) -> AnalyzerModel:
        files = request_files(data_service.get_data(), ptr, contents=False, uast=True)
        return func(cls, ptr, config, data_service, files=files, **data)

    return wrapped_with_uasts


def with_uasts_and_contents(func):  # noqa: D401
    """
    Decorator to provide "files" keyword argument to `**data` in `Analyzer.train()`.

    "files" are the list of `File`-s with all the UASTs and raw file contents for the passed Git
    repository URL and revision, see lookout/core/server/sdk/service_data.proto.

    :param func: Method with the signature compatible with `Analyzer.train()`.
    :return: The decorated method.
    """
    @functools.wraps(func)
    @_handle_rpc_errors
    def wrapped_with_uasts_and_contents(cls: Type[Analyzer], ptr: ReferencePointer, config: dict,
                                        data_service: DataService, **data) -> AnalyzerModel:
        files = request_files(data_service.get_data(), ptr, contents=True, uast=True)
        return func(cls, ptr, config, data_service, files=files, **data)

    return wrapped_with_uasts_and_contents


def request_changes(stub: DataStub, ptr_from: ReferencePointer, ptr_to: ReferencePointer,
                    contents: bool, uast: bool) -> Iterable[Change]:
    """
    Invoke GRPC API and get the changes. Used by `with_changed_uasts()` and Review events.

    :return: The stream of the gRPC invocation results. In theory, `.result()` would turn this \
             into a synchronous call, but in practice, that function call hangs for some reason.
    """
    request = ChangesRequest(base=ptr_from.to_pb(), head=ptr_to.to_pb())
    request.exclude_pattern = GARBAGE_PATTERN
    request.exclude_vendored = True
    request.want_contents = contents
    request.want_uast = uast
    return stub.GetChanges(request)


def request_files(stub: DataStub, ptr: ReferencePointer, contents: bool, uast: bool
                  ) -> Iterable[File]:
    """
    Invoke GRPC API and get the files. Used by `with_uasts()` and Push events.

    :return: The stream of the gRPC invocation results.
    """
    request = FilesRequest(revision=ptr.to_pb())
    request.exclude_pattern = GARBAGE_PATTERN
    request.exclude_vendored = True
    request.want_contents = contents
    request.want_uast = uast
    return stub.GetFiles(request)


def parse_uast(stub: bblfsh.aliases.ProtocolServiceStub, code: str, filename: str,
               language: Optional[str] = None) -> Tuple[bblfsh.Node, list]:
    """
    Return UAST for given file contents and name.

    :param stub: The Babelfish protocol stub.
    :param code: The contents of the file.
    :param filename: The name of the file, can be a full path.
    :param language: The name of the language. It is not required to set: Babelfish can \
                     autodetect it.
    :return: The parsed UAST or undefined object if there was an error; the list of parsing errors.
    """
    request = bblfsh.aliases.ParseRequest(filename=os.path.basename(filename), content=code,
                                          language=language)
    response = stub.Parse(request)
    return response.uast, response.errors
