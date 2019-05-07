import unittest

import requests

from lookout.core.metrics import start_prometheus, submit_event
from lookout.core.metrics.server import ConfidentGauge, ConfidentSummary, RollingStats


class MetricReader:
    def __init__(self, port, addr="localhost"):
        self.__is_running = False
        self.__port = port
        self.__addr = addr
        self.__metrics = {}
        self.__data = {}

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
    def data(self) -> dict:
        return self.__data

    def query_data(self, addr: str = None, port: int = None) -> str:

        addr = self.addr if addr is None else addr
        port = self.port if port is None else port
        api_endpoint = "http://{}:{}".format(addr, port)
        r = requests.get(url=api_endpoint)
        if r.status_code == 200:
            data = r.content.decode()
            return data
        else:
            raise ValueError(
                "\nGot status code {} when querying the server."
                " Reponse content: {}\n".format(r.status_code, r.content.decode())
            )

    @staticmethod
    def parse_response(data: str):
        lines = data.split("\n")

        def is_metric_line(line: str):
            return not (line.startswith("#") or line.startswith("python") or line == "")

        def parse_line(line):

            try:
                name, val = line.split(" ")
            except ValueError:
                return line, None
            try:
                val = float(val)
            except ValueError:
                pass
            return name, val

        raw_metrics = [l for l in lines if is_metric_line(l)]
        metric_values = [parse_line(l) for l in raw_metrics]
        metrics = {name: val for name, val in metric_values}
        return metrics

    def parse_data(self, addr: str = None, port: int = None):
        decoded_response = self.query_data(addr=addr, port=port)
        self.__data = self.parse_response(decoded_response)
        self.__metrics = {
            name: val for name, val in self.__data.items() if not name.startswith("process_")
        }

    def query_metrics(self, name: str):
        return {k: v for k, v in self.metrics.items() if name in k}


def dummy_server():
    from lookout.core.metrics.server import PROMETHEUS_SERVER as server

    if server is None:
        try:
            start_prometheus(8000)
        except OSError as e:
            raise e
        from lookout.core.metrics.server import PROMETHEUS_SERVER as server
    assert server is not None
    return server


class TestMetrics(unittest.TestCase):
    def test_kahan_algorithm(self):
        metric = ConfidentGauge("test_data_kahan", "running counters")
        ix = 0
        val = 0.001
        for _ in range(10000):
            ix += val
            metric.inc(val)

        metric_val = metric.collect()[0].samples[-1].value
        self.assertEqual(metric_val, 10.0)
        self.assertNotEqual(metric, ix)

    def test_multithread(self):
        #  TODO: find out the correct way to test Kahan inside a multi thread.
        pass


class TestPrometheusServer(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = MetricReader(8000)
        self.server = dummy_server()

    def test_submit_event_gauge(self):
        name = "test_gauge_160290"
        val = 160290
        self.server.submit_event(key=name, value=val, metric_type=ConfidentGauge)
        self.reader.parse_data()
        self.assertTrue(name in self.reader.metrics.keys())
        self.assertEqual(self.reader.metrics[name], val)

    def test_submit_summary(self):
        name = "test_summary"
        val = 3
        self.server.submit_event(
            key=name, value=val, metric_type=ConfidentSummary, update_method="observe"
        )
        self.reader.parse_data()
        self.assertTrue("{}_sum".format(name) in list(self.reader.metrics.keys()))
        self.assertTrue("{}_count".format(name) in list(self.reader.metrics.keys()))
        self.assertEqual(self.reader.metrics["{}_count".format(name)], 1)
        self.assertEqual(self.reader.metrics["{}_sum".format(name)], 3)

        val = 4
        self.server.submit_event(key=name, value=val, update_method="observe")
        self.reader.parse_data()
        self.assertTrue("{}_sum".format(name) in list(self.reader.metrics.keys()))
        self.assertTrue("{}_count".format(name) in list(self.reader.metrics.keys()))
        self.assertEqual(self.reader.metrics["{}_count".format(name)], 2)
        self.assertEqual(self.reader.metrics["{}_sum".format(name)], 7)

    def test_submit_rolling_stats(self):
        name = "test_rolling_stats"
        val = 4
        self.server.submit_event(key=name, value=val, metric_type=RollingStats)
        val = 6
        self.server.submit_event(key=name, value=val)
        self.reader.parse_data()
        self.assertTrue("{}_sum".format(name) in list(self.reader.metrics.keys()))
        self.assertTrue("{}_count".format(name) in list(self.reader.metrics.keys()))
        self.assertTrue(self.reader.metrics["{}_count".format(name)] == 2)
        self.assertTrue(self.reader.metrics["{}_sum".format(name)] == 10)
        self.assertTrue(self.reader.metrics["{}_sum_of_squares".format(name)] == 52)


class TestSubmitEvent(unittest.TestCase):
    def setUp(self) -> None:
        self.server = dummy_server()
        self.reader = MetricReader(8000)

    def test_send_new_scalar(self):
        name = "a_float"
        submit_event(name, 3.1)
        self.reader.parse_data()
        self.assertTrue(self.reader.metrics["{}_sum".format(name)] == 3.1)
        submit_event(name, 5.1)
        self.reader.parse_data()
        self.assertTrue(self.reader.metrics["{}_sum".format(name)] == 8.2)

    def test_new_gauge(self):
        name = "gauge_test"
        submit_event(name, 3.1, metric_type=ConfidentGauge)
        submit_event(name, 7.1)
        self.reader.parse_data()
        self.assertTrue(
            self.reader.metrics["{}".format(name)] == 10.2, str(self.reader.query_metrics(name))
        )

        submit_event(name, 777, update_method="set")
        self.reader.parse_data()
        self.assertTrue(self.reader.metrics["{}".format(name)] == 777)
