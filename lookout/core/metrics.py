import os
from threading import Lock
from typing import Union

from prometheus_client import start_http_server
from prometheus_client.metrics import MetricWrapperBase


PROMETHEUS_SERVER = None

PROMETHEUS_HOST = os.getenv("PROMETHEUS_HOST", "0.0.0.0")

PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "8000"))


class MutexValue:
    """A float protected by a mutex."""

    _multiprocess = False

    def __init__(self, typ, metric_name, name, labelnames, labelvalues, **kwargs):
        """Store values protected by a lock."""
        self._value = 0.0
        self._lock = Lock()
        self._interm_sum = 0

    def add(self, amount):
        """Increase the value by the given amount."""
        with self._lock:
            summ = self._value
            y = amount - self._interm_sum
            t = summ + y
            self._interm_sum = (t - summ) - y
            self._value = t

    def set(self, value):
        """Set the value to a given amount."""
        with self._lock:
            self._interm_sum = 0
            self._value = value

    def get(self):
        """Read the internal value."""
        with self._lock:
            return self._value


class ConfidentCounter(MetricWrapperBase):
    """It stores the count, cumulative sum, and the cumulative sum of squares of a variable.

    It makes it possible to calculate the rolling mean and standard deviation
    of a time series.
    """

    _type = "counter"

    def _metric_init(self):
        self._count = MutexValue(
            self._type, self._name, self._name + "_count", self._labelnames, self._labelvalues,
        )
        self._sum = MutexValue(
            self._type, self._name, self._name + "_sum", self._labelnames, self._labelvalues,
        )

        self._square = MutexValue(
            self._type,
            self._name,
            self._name + "_sum_of_squares",
            self._labelnames,
            self._labelvalues,
        )

    def add(self, amount):
        """Keep track of the given value."""
        self._count.add(1)
        self._sum.add(amount)
        self._square.add(amount ** 2)

    def _child_samples(self):
        count = max(self._count.get(), 1)
        _sum = self._sum.get()
        square = self._square.get()
        return ("_count", {}, count), ("_sum", {}, _sum), ("_sum_of_squares", {}, square)


def start_prometheus(port: int = PROMETHEUS_PORT, addr: str = PROMETHEUS_HOST):
    """Start the prometheus HTTP Server in the target port and address.

    The stored metrics will be accessible at http://addr:port.

    :param port: Target port to run the PrometheusServer.
    :param addr: IP address of the PrometheusServer. It defaults to locahost.
    :return: None
    """
    global PROMETHEUS_SERVER
    if PROMETHEUS_SERVER is None:
        PROMETHEUS_SERVER = PrometheusServer(port=port, addr=addr)
        PROMETHEUS_SERVER.start_http_server()
    elif not PROMETHEUS_SERVER.is_running:
        PROMETHEUS_SERVER.start_http_server()


def submit_event(key: str, value: Union[int, float, bool], labelnames: str = ""):
    """Register an event by a key and with a numeric value.

    If the key does not exist, it creates a new Prometheus Metric.

    :param key: Identifier of the event.
    :param value: Value of the event. It will convert cast variables to int.
    :param labelnames: Additional description of the event. Only used when creating a new event.
    :return: None
    """
    start_prometheus()
    if PROMETHEUS_SERVER is not None:
        PROMETHEUS_SERVER.submit_event(key=key, value=value, labelnames=labelnames)
    else:
        raise ValueError(
            "PrometheusServer is not started yet, please call start_prometheus() first.",
        )


class PrometheusServer:
    """Manage the streaming process for different metrics."""

    def __init__(self, port=PROMETHEUS_PORT, addr=PROMETHEUS_HOST):
        """
         Manage the streaming process for different metrics.

        :param port:
        :param addr:
        """
        self._is_running = False
        self._port = port
        self._addr = addr
        self._metrics = {}

    @property
    def port(self) -> int:
        """Return the port where the server is running."""
        return self._port

    @property
    def addr(self) -> str:
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
        start_http_server(port=self.port, addr=self.addr)
        self._is_running = True

    def create_new_metric(self, name: str, labelnames: str = "", *args, **kwargs):
        """Create a new metric in case it does not previously exists.

        :param name: It will be used as a key to identify the new metric.
        :param labelnames: Additional description of the event. Only used when creating a new
            event.
        :param args: Additional args to initialize the target metric_type.
        :param kwargs: Additional kwargs to initialize the target metric_type.
        :return: None
        """
        self.metrics[name] = ConfidentCounter(name, labelnames, *args, **kwargs)

    def submit_event(self, key: str, value: Union[int, float, bool], *args, **kwargs):
        """Register an event by a key and with a numeric value.

         If the key does not exist, it creates a new Prometheus Metric.

        :param key: Identifier of the event.
        :param value: Value of the event. It will convert cast variables to int.
        :param args: Additional args to initialize the target metric_type. Ignored if no new metric
            is created.
        :param kwargs: Additional kwargs to initialize the target metric_type. Ignored if no new
            metric is created.
        :return: None
        """
        if key not in self.metrics:
            self.create_new_metric(name=key, *args, **kwargs)
        value = int(value) if isinstance(value, bool) else value
        self.metrics[key].add(value)
