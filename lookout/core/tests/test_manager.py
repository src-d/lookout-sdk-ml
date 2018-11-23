from typing import Tuple
import unittest

import bblfsh
from google.protobuf.struct_pb2 import Struct as ProtobufStruct

from lookout.core.analyzer import Analyzer, AnalyzerModel, DummyAnalyzerModel, ReferencePointer
from lookout.core.api.event_pb2 import PushEvent, ReviewEvent
from lookout.core.api.service_analyzer_pb2 import Comment, EventResponse
from lookout.core.api.service_data_pb2_grpc import DataStub
from lookout.core.data_requests import DataService
from lookout.core.manager import AnalyzerManager
from lookout.core.model_repository import ModelRepository
from lookout.core.ports import Type


class FakeModel(AnalyzerModel):
    def _generate_tree(self) -> dict:
        return {}

    def _load_tree(self, tree: dict) -> None:
        pass


class FakeAnalyzer(Analyzer):
    version = "1"
    model_type = FakeModel
    name = "fake.analyzer.FakeAnalyzer"
    instance = None
    service = None

    def __init__(self, model: AnalyzerModel, url: str, config: dict):
        super().__init__(model, url, config)
        FakeAnalyzer.instance = self

    def analyze(self, ptr_from: ReferencePointer, ptr_to: ReferencePointer,
                data_service: DataService, **data) -> [Comment]:
        comment = Comment()
        comment.text = "%s|%s" % (ptr_from.commit, ptr_to.commit)
        FakeAnalyzer.service = data_service
        return [comment]

    @classmethod
    def train(cls, ptr: ReferencePointer, config: dict, data_service: DataService, **data
              ) -> AnalyzerModel:
        cls.service = data_service
        return FakeModel()


class FakeDummyAnalyzer(Analyzer):
    version = "1"
    model_type = DummyAnalyzerModel
    name = "fake.analyzer.FakeDummyAnalyzer"
    instance = None
    trained = False

    def __init__(self, model: AnalyzerModel, url: str, config: dict):
        super().__init__(model, url, config)
        self.analyzed = False
        self.trained = False
        FakeDummyAnalyzer.instance = self

    def analyze(self, ptr_from: ReferencePointer, ptr_to: ReferencePointer,
                data_service: DataService, **data) -> [Comment]:
        self.analyzed = True
        return []

    @classmethod
    def train(cls, ptr: ReferencePointer, config: dict, data_service: DataService, **data
              ) -> AnalyzerModel:
        cls.trained = True
        return DummyAnalyzerModel()


class FakeDataService:
    def get_data(self) -> DataStub:
        return "XXX"

    def get_bblfsh(self) -> bblfsh.aliases.ProtocolServiceStub:
        return "YYY"

    def shutdown(self):
        pass


class FakeModelRepository(ModelRepository):
    def __init__(self):
        self.get_calls = []
        self.set_calls = []

    def get(self, model_id: str, model_type: Type[AnalyzerModel], url: str
            ) -> Tuple[AnalyzerModel, bool]:
        self.get_calls.append((model_id, model_type, url))
        return FakeModel(), True

    def set(self, model_id: str, url: str, model: AnalyzerModel):
        self.set_calls.append((model_id, url, model))

    def init(self):
        pass

    def shutdown(self):
        pass


class AnalyzerManagerTests(unittest.TestCase):
    def setUp(self):
        self.data_service = FakeDataService()
        self.model_repository = FakeModelRepository()
        self.manager = AnalyzerManager(
            [FakeAnalyzer, FakeAnalyzer, FakeDummyAnalyzer],
            self.model_repository, self.data_service)
        FakeAnalyzer.stub = None

    def test_process_review_event(self):
        request = ReviewEvent()
        request.configuration.update({"fake.analyzer.FakeAnalyzer": {"one": "two"}})
        request.commit_revision.base.internal_repository_url = "foo"
        request.commit_revision.base.reference_name = "refs/heads/master"
        request.commit_revision.base.hash = "00" * 20
        request.commit_revision.head.internal_repository_url = "bar"
        request.commit_revision.head.reference_name = "refs/heads/master"
        request.commit_revision.head.hash = "ff" * 20
        response = self.manager.process_review_event(request)
        self.assertIsInstance(response, EventResponse)
        self.assertEqual(response.analyzer_version, "fake.analyzer.FakeAnalyzer/1 "
                                                    "fake.analyzer.FakeAnalyzer/1 "
                                                    "fake.analyzer.FakeDummyAnalyzer/1")
        self.assertEqual(len(response.comments), 2)
        self.assertEqual(*response.comments)
        self.assertEqual(response.comments[0].text, "%s|%s" % ("00" * 20, "ff" * 20))
        self.assertEqual(self.model_repository.get_calls,
                         [("fake.analyzer.FakeAnalyzer/1", FakeModel, "foo")] * 2)
        self.assertEqual(FakeAnalyzer.instance.config["one"], "two")
        self.assertEqual(FakeAnalyzer.service.get_data(), "XXX")
        self.assertTrue(FakeDummyAnalyzer.instance.analyzed)

    def test_process_push_event(self):
        request = PushEvent()
        request.commit_revision.head.internal_repository_url = "wow"
        request.commit_revision.head.reference_name = "refs/heads/master"
        request.commit_revision.head.hash = "80" * 20
        response = self.manager.process_push_event(request)
        self.assertIsInstance(response, EventResponse)
        self.assertEqual(response.analyzer_version, "fake.analyzer.FakeAnalyzer/1 "
                                                    "fake.analyzer.FakeAnalyzer/1 "
                                                    "fake.analyzer.FakeDummyAnalyzer/1")
        self.assertEqual(len(response.comments), 0)
        self.assertEqual(len(self.model_repository.set_calls), 2)
        self.assertEqual(self.model_repository.set_calls[0][:2],
                         ("fake.analyzer.FakeAnalyzer/1", "wow"))
        self.assertIsInstance(self.model_repository.set_calls[0][2], FakeModel)
        self.assertEqual(self.model_repository.set_calls[1][:2],
                         ("fake.analyzer.FakeAnalyzer/1", "wow"))
        self.assertIsInstance(self.model_repository.set_calls[1][2], FakeModel)
        self.assertEqual(FakeAnalyzer.service.get_bblfsh(), "YYY")
        self.assertFalse(FakeDummyAnalyzer.trained)


class AnalyzerManagerUtilsTests(unittest.TestCase):
    def test_protobuf_struct_to_dict(self):
        struct_to_dict = AnalyzerManager._protobuf_struct_to_dict
        proto_struct = ProtobufStruct()
        self.assertEqual(struct_to_dict(proto_struct), {})
        proto_struct["a"] = 1.
        self.assertEqual(struct_to_dict(proto_struct), {"a": 1.})
        proto_struct["b"] = {}  # converts to ProtobufStruct automatically
        self.assertEqual(struct_to_dict(proto_struct), {"a": 1., "b": {}})
        proto_struct["b"]["c"] = 2.
        self.assertEqual(struct_to_dict(proto_struct), {"a": 1., "b": {"c": 2.}})
        proto_struct["b"]["d"] = []  # converts to Protobuf List automatically
        self.assertEqual(struct_to_dict(proto_struct), {"a": 1., "b": {"c": 2., "d": []}})
        proto_struct["b"]["d"].append(3.)
        self.assertEqual(struct_to_dict(proto_struct), {"a": 1., "b": {"c": 2., "d": [3.]}})
        proto_struct["b"]["d"].append({})  # converts to ProtobufStruct automatically
        self.assertEqual(struct_to_dict(proto_struct), {"a": 1., "b": {"c": 2., "d": [3., {}]}})
        proto_struct["b"]["d"][1]["e"] = 4.
        self.assertEqual(struct_to_dict(proto_struct),
                         {"a": 1., "b": {"c": 2., "d": [3., {"e": 4.}]}})


if __name__ == "__main__":
    unittest.main()
