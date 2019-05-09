import threading
import unittest

import requests

from lookout.core.metrics import ConfidentCounter, PreciseFloat, submit_event


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

        raise ValueError(
            "\nGot status code {} when querying the server."
            " Reponse content: {}\n".format(r.status_code, r.content.decode()),
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
    from lookout.core.metrics import _prometheus_server as server

    if server is None:
        try:
            submit_event("start_server_hack", 8000)
        except OSError as e:
            raise e
        from lookout.core.metrics import _prometheus_server as server
    assert server is not None
    return server


class TestConfidentCounter(unittest.TestCase):
    def test_kahan_algorithm(self):
        metric = ConfidentCounter("test_data_kahan", "running counters")
        # why this number? https://en.wikipedia.org/wiki/Double-precision_floating-point_format
        origin = brute_sum = 4503599627370496  # 4_503_599_627_370_496
        metric += origin
        val = 0.001
        for _ in range(1000):
            brute_sum += val
            metric += val

        metric_val = metric.collect()[0].samples[1].value
        self.assertEqual(metric_val, origin + 1.)
        self.assertNotEqual(brute_sum, origin + 1)

    def test_get(self):
        metric = ConfidentCounter("test_get_counter", "running counters")
        metric += 10
        self.assertEqual(metric._count.get(), 1)
        self.assertEqual(metric._sum.get(), 10)
        self.assertEqual(metric._sum_of_squares.get(), 100)

    def test_set(self):
        metric = ConfidentCounter("test_set_counter", "running counters")
        metric._count.set(1)
        metric._sum.set(10)
        metric._sum_of_squares.set(100)
        self.assertEqual(metric._count.get(), 1)
        self.assertEqual(metric._sum.get(), 10)
        self.assertEqual(metric._sum_of_squares.get(), 100)

    def test_multithread(self):
        x = PreciseFloat()
        threads = []

        def bump():
            nonlocal x
            for _ in range(1000):
                x += 1

        for _ in range(100):
            t = threading.Thread(target=bump)
            t.start()
            threads.append(t)

        for i in range(100):
            threads[i].join()
        self.assertEqual(x.get(), 100 * 1000)


class TestPrometheusServer(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = MetricReader(8000)
        self.server = dummy_server()

    def test_attributes(self):
        self.assertIsInstance(self.server.metrics, dict)
        self.assertIsInstance(self.server.host, str)
        self.assertIsInstance(self.server.port, int)

    def test_filter_metric_name(self):
        valid_name = "miau.gdb"
        filtered = self.server._adjust_metric_name(name=valid_name)
        self.assertEqual(filtered, "miau:gdb")
        with self.assertRaises(ValueError):
            invalid_name = "!AM!?wilto%."
            self.server._adjust_metric_name(name=invalid_name)
            # match = self.server._valid_name_regex.match(invalid_name)
            # self.assertEqual(filtered, match)

    def test_submit_rolling_stats(self):
        name = "test_rolling_stats"
        val = 4
        self.server.submit_event(key=name, value=val)
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
