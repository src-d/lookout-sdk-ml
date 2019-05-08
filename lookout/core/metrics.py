import os
import re
from threading import Lock
from typing import Union

from prometheus_client import start_http_server
from prometheus_client.metrics import MetricWrapperBase


_prometheus_server = None
PROMETHEUS_HOST = os.getenv("PROMETHEUS_HOST", "0.0.0.0")
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "8000"))


class PreciseFloat:
    """A float protected by a mutex."""

    def __init__(self):
        """Store values protected by a lock."""
        self._value = 0.0
        self._aux = 0
        self._lock = Lock()

    def __iadd__(self, amount):
        """Increase the value by the given amount."""
        with self._lock:
            val = self._value
            y = amount - self._aux
            t = val + y
            self._aux = (t - val) - y
            self._value = t
        return self

    def set(self, value):
        """Set the value to a given amount."""
        with self._lock:
            self._aux = 0
            self._value = value

    def get(self):
        """Read the current value."""
        with self._lock:
            return self._value


class ConfidentCounter(MetricWrapperBase):
    """It stores the count, cumulative sum, and the cumulative sum of squares of a variable.

    It makes it possible to calculate the rolling mean and standard deviation
    of a time series.
    """

    _type = "counter"

    def _metric_init(self):
        self._count = PreciseFloat()
        self._sum = PreciseFloat()
        self._square = PreciseFloat()

    def __iadd__(self, amount):
        """Keep track of the given value."""
        self._count += 1
        self._sum += amount
        self._square += amount ** 2
        return self

    def _child_samples(self):
        count = self._count.get()
        _sum = self._sum.get()
        square = self._square.get()
        return ("_count", {}, count), ("_sum", {}, _sum), ("_sum_of_squares", {}, square)


def start_prometheus(host: str, port: int):
    """Start the prometheus HTTP Server in the target port and address.

    The stored metrics will be accessible at http://addr:port.

    :param port: Target port to run the PrometheusServer.
    :param host: IP address of the PrometheusServer. It defaults to locahost.
    :return: None
    """
    global _prometheus_server
    if _prometheus_server is None:
        _prometheus_server = PrometheusServer(port=port, host=host)
        _prometheus_server.start_http_server()
    elif not _prometheus_server.is_running:
        _prometheus_server.start_http_server()


def submit_event(key: str, value: Union[int, float, bool], labelnames: str = ""):
    """Register an event by a key and with a numeric value.

    If the key does not exist, it creates a new Prometheus Metric.

    :param key: Identifier of the event.
    :param value: Value of the event. It will convert cast variables to int.
    :param labelnames: Additional description of the event. Only used when creating a new event.
    :return: None
    """
    start_prometheus(host=PROMETHEUS_HOST, port=PROMETHEUS_PORT)
    if _prometheus_server is not None:
        _prometheus_server.submit_event(key=key, value=value, labelnames=labelnames)
    else:
        raise ValueError(
            "PrometheusServer is not started yet, please call start_prometheus() first.",
        )


class PrometheusServer:
    """Manage the streaming process for different metrics."""

    _valid_name_regex = re.compile("[a-zA-Z_:][a-zA-Z0-9_:]*")

    def __init__(self, host: str, port: int):
        """
         Manage the streaming process for different metrics.

        :param port: Port where the server will be accessible.
        :param host: Address where the server will be accessible.
        """
        self._is_running = False
        self._port = port
        self._addr = host
        self._metrics = {}

    @property
    def port(self) -> int:
        """Return the port where the server is running."""
        return self._port

    @property
    def host(self) -> str:
        """Return the address where the server is running."""
        return self._addr

    @property
    def metrics(self) -> dict:
        """Return the metrics stored in the server."""
        return self._metrics

    @property
    def is_running(self) -> bool:
        """Return True if the server is running."""
        return self._is_running

    def start_http_server(self):
        """Start the HTTP server."""
        start_http_server(port=self.port, addr=self.host)
        self._is_running = True

    def create_new_metric(self, name: str, labelnames: str = ""):
        """Create a new metric in case it does not previously exists.

        :param name: It will be used as a key to identify the new metric.
        :param labelnames: Additional description of the event. Only used when creating a new
            event.
        :return: None
        """
        self.metrics[name] = ConfidentCounter(name, labelnames)

    def _filter_metric_name(self, name: str):
        orig_name = name
        name = name.replace(".", ":")

        if not self._valid_name_regex.match(name):
            raise ValueError("%s is an invalid event name" % orig_name)
        return name

    def submit_event(self, key: str, value: Union[int, float, bool], labelnames: str = ""):
        """Register an event by a key and with a numeric value.

         If the key does not exist, it creates a new Prometheus Metric.

        :param key: Identifier of the event.
        :param value: Value of the event. It will convert cast variables to int.
        :param labelnames: Additional description of the event. Only used when creating a new
            event.
        :return: None
        """
        key = self._filter_metric_name(key)
        if key not in self.metrics:
            self.create_new_metric(name=key, labelnames=labelnames)
        value = int(value) if isinstance(value, bool) else value
        self.metrics[key] += value
