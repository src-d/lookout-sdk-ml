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
    """A floating-point value.

    It is possible to add numbers to it, and the result is guaranteed to be precise
    thanks to Kahan summation algorithm. That addition operation is thread safe.

    """

    def __init__(self):
        """Initialize a new instance of PreciseFloat."""
        self._value = 0.0
        self._aux = 0
        self._lock = Lock()

    def __iadd__(self, amount):
        """Increase the value by the given amount. Thread safe. No precision loss."""
        with self._lock:
            val = self._value
            y = amount - self._aux
            t = val + y
            self._aux = (t - val) - y
            self._value = t
        return self

    def set(self, value):
        """Set the value to the given amount. Thread safe."""
        with self._lock:
            self._aux = 0
            self._value = value

    def get(self):
        """Read the current value. Thread safe."""
        with self._lock:
            return self._value


class ConfidentCounter(MetricWrapperBase):
    """Prometheus Counter-like class.

    It enables calculation of the rolling mean, and standard deviation.
    This class internally reports the number of events, the sum of event values,
    and the sum of squares of event values to Prometheus.
    """

    _type = "counter"

    def __iadd__(self, amount):
        """Add a delta value to the counter."""
        self._count += 1
        self._sum += amount
        self._sum_of_squares += amount ** 2
        return self

    def _metric_init(self):
        self._count = PreciseFloat()
        self._sum = PreciseFloat()
        self._sum_of_squares = PreciseFloat()

    def _child_samples(self):
        return (
            ("_count", {}, self._count.get()),
            ("_sum", {}, self._sum.get()),
            ("_sum_of_squares", {}, self._sum_of_squares.get()),
        )


def submit_event(key: str, value: Union[int, float, bool], description: str = ""):
    """Register an event by a key and with a numeric value.

    If the key does not exist, it creates a new Prometheus Metric.

    :param key: Identifier of the event.
    :param value: Value of the event. It will convert cast variables to int.
    :param description: Additional description of the event. Only used when creating a new event.
    :return: None
    """
    global _prometheus_server
    if _prometheus_server is None:
        _prometheus_server = PrometheusServer(host=PROMETHEUS_HOST, port=PROMETHEUS_PORT)
    _prometheus_server.submit_event(key=key, value=value, description=description)


class PrometheusServer:
    """Manage the streaming process for different metrics."""

    _valid_name_regex = r"[a-zA-Z_:][a-zA-Z0-9_:]*"

    def __init__(self, host: str, port: int):
        """
         Manage the streaming process for different metrics.

        :param port: Port where the server will be accessible.
        :param host: Address where the server will be accessible.
        """
        self._port = port
        self._addr = host
        self._metrics = {}
        start_http_server(port=self.port, addr=self.host)

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

    def create_new_metric(self, name: str, description: str = ""):
        """Create a new metric in case it does not previously exists.

        :param name: It will be used as a key to identify the new metric.
        :param description: Additional description of the event. Only used when creating a new
            event.
        :return: None
        """
        self.metrics[name] = ConfidentCounter(name, description)

    def _adjust_metric_name(self, name: str) -> str:
        orig_name = name
        name = name.replace(".", ":")

        if not re.match(self._valid_name_regex, name):
            raise ValueError("%s is an invalid event name" % orig_name)
        return name

    def submit_event(self, key: str, value: Union[int, float, bool], description: str = ""):
        """Register an event by a key and with a numeric value.

         If the key does not exist, it creates a new Prometheus Metric.

        :param key: Identifier of the event.
        :param value: Value of the event. It will convert cast variables to int.
        :param description: Additional description of the event. Only used when creating a new
            event.
        :return: None
        """
        key = self._adjust_metric_name(key)
        if key not in self.metrics:
            self.create_new_metric(name=key, description=description)
        self.metrics[key] += float(value)
