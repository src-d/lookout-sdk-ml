import time
from typing import Callable, Union

from prometheus_client import core, Counter, Gauge, start_http_server, Summary

from lookout.core.metrics import values


PROMETHEUS_SERVER = None


class ConfidentGauge(Gauge):
    def _metric_init(self):
        self._value = values.ValueClass(
            self._type,
            self._name,
            self._name,
            self._labelnames,
            self._labelvalues,
            multiprocess_mode=self._multiprocess_mode,
        )


class ConfidentCounter(Counter):
    def _metric_init(self):
        self._value = values.ValueClass(
            self._type, self._name, self._name + "_total", self._labelnames, self._labelvalues
        )
        self._created = time.time()


class ConfidentSummary(Summary):
    def _metric_init(self):
        self._count = values.ValueClass(
            self._type, self._name, self._name + "_count", self._labelnames, self._labelvalues
        )
        self._sum = values.ValueClass(
            self._type, self._name, self._name + "_sum", self._labelnames, self._labelvalues
        )
        self._created = time.time()


class RollingStats(ConfidentSummary):
    """It stores the count, the cumulative sum and, the cumulative sum of squares of the
    observed variable. It makes it possible to calculate the rolling mean and standard deviation
    of a time series.
    """

    def _metric_init(self):
        super(RollingStats, self)._metric_init()
        self._square = values.ValueClass(
            self._type,
            self._name,
            self._name + "_sum_of_squares",
            self._labelnames,
            self._labelvalues,
        )

    def observe(self, amount):
        """Observe the given amount."""
        super(RollingStats, self).observe(amount=amount)
        self._square.inc(amount ** 2)

    def _child_samples(self):
        count = max(self._count.get(), 1)
        _sum = self._sum.get()
        square = self._square.get()
        return ("_count", {}, count), ("_sum", {}, _sum), ("_sum_of_squares", {}, square)


def start_prometheus(port: int, addr: str = "", **kwargs):
    """
    Start the prometheus HTTP Server in the target port and address. The stored metrics will be
    accessible at http://addr:port.

    :param port: Target port to run the PrometheusServer.
    :param addr: IP address of the PrometheusServer. It defaults to locahost.
    :param kwargs: Additional keyword arguments to initialize the server. Not used by default.
    :return: None
    """
    global PROMETHEUS_SERVER
    PROMETHEUS_SERVER = PrometheusServer(port=port, addr=addr, **kwargs)
    PROMETHEUS_SERVER.start_http_server()


def submit_event(
    key: str,
    value: Union[int, float, bool],
    labelnames: str = "",
    metric_type: Callable = RollingStats,
    update_method=None,
    *args,
    **kwargs,
):
    """Register an event by a key and with a numeric value. If the key does not exist, it creates a
    new Prometheus Metric.

    :param key: Identifier of the event.
    :param value: Value of the event. It will convert cast variables to int.
    :param labelnames: Additional description of the event. Only used when creating a new event.
    :param metric_type: Type of metric that will be used to register the target value. Only used
        when creating a new event.
    :param update_method: Function to be called on the target metric to update the values. If None
        it will try to apply update the metric calling observe(), inc() if observe is not
        available, and set() if inc is not available.
    :return: None
    """
    if PROMETHEUS_SERVER is not None:
        PROMETHEUS_SERVER.submit_event(
            key=key,
            value=value,
            labelnames=labelnames,
            metric_type=metric_type,
            update_method=update_method,
            *args,
            **kwargs,
        )
    else:
        raise ValueError(
            "PrometheusServer is not started yet, please call start_prometheus() first."
        )


class PrometheusServer:
    def __init__(
        self, port, addr="", registry=core.REGISTRY, default_metric: Callable = RollingStats
    ):
        """
         Manage the streaming process for different metrics.

        :param port:
        :param addr:
        :param registry:
        :param default_metric:
        """
        self.__is_running = False
        self.__port = port
        self.__addr = addr
        self.__metrics = {}
        self.__registry = registry
        self.default_metric = default_metric

    @property
    def registry(self):
        return self.__registry

    @property
    def port(self) -> int:
        return self.__port

    @property
    def addr(self) -> str:
        return self.__addr

    @property
    def metrics(self) -> dict:
        return self.__metrics

    @property
    def is_running(self) -> bool:
        return self.__is_running

    def start_http_server(self):
        start_http_server(port=self.port, addr=self.addr, registry=self.registry)
        self.__is_running = True

    def create_new_metric(
        self, name: str, labelnames: str = "", metric_type=None, *args, **kwargs
    ):
        """Create a new metric in case it does not preivously exists.

        :param name: It will be used as a key to identify the new metric.
        :param labelnames: Additional description of the event. Only used when creating a new
            event.
        :param metric_type: Type of metric that will be used to register the target value. Only
            used when creating a new event.
        :param args: Additional args to initialize the target metric_type.
        :param kwargs: Additional kwargs to initialize the target metric_type.
        :return: None
        """
        metric_type = self.default_metric if metric_type is None else metric_type
        self.metrics[name] = metric_type(name, labelnames, registry=self.registry, *args, **kwargs)

    def submit_event(
        self,
        key: str,
        value: Union[int, float, bool],
        update_method: str = None,
        metric_type: Callable = None,
        *args,
        **kwargs,
    ):
        """Register an event by a key and with a numeric value. If the key does not exist, it
        creates a new Prometheus Metric.

        :param key: Identifier of the event.
        :param value: Value of the event. It will convert cast variables to int.
        :param metric_type: Type of metric that will be used to register the target value. Only
            used when creating a new event.
        :param update_method: Function to be called on the target metric to update the values.
            If None it will try to apply update the metric calling observe(), inc() if
            observe is not available, and set() if inc is not available.
        :param args: Additional args to initialize the target metric_type. Ignored if no new metric
            is created.
        :param kwargs: Additional kwargs to initialize the target metric_type. Ignored if no new
            metric is created.
        :return: None
        """
        if key not in self.metrics.keys():
            self.create_new_metric(name=key, metric_type=metric_type, *args, **kwargs)
        value = int(value) if isinstance(value, bool) else value
        if hasattr(self.metrics[key], "observe") and update_method is None:
            self.metrics[key].observe(value)
        elif update_method is None and hasattr(self.metrics[key], "inc"):
            self.metrics[key].inc(value)
        elif update_method is None and hasattr(self.metrics[key], "set"):
            self.metrics[key].set(value)
        elif update_method is not None:
            getattr(self.metrics[key], update_method)(value)
        else:
            raise ValueError(
                "Please specify a compatible update method for the target metric. {}".format(
                    type(self.metrics[key])
                )
            )
