import logging
from typing import Any, Dict, Iterable

from bblfsh import Node

from lookout.core.analyzer import Analyzer, AnalyzerModel, ReferencePointer
from lookout.core.api.service_analyzer_pb2 import Comment
from lookout.core.api.service_data_pb2 import Change, File
from lookout.core.data_requests import DataService, \
    with_changed_uasts_and_contents, with_uasts_and_contents


class MyModel(AnalyzerModel):  # noqa: D
    NAME = "my-model"
    VENDOR = "source{d}"

    def _load_tree(self, tree: dict) -> None:
        self.node_counts = tree["node_counts"]

    def _generate_tree(self) -> dict:
        return {"node_counts": self.node_counts}


class MyAnalyzer(Analyzer):  # noqa: D
    model_type = MyModel
    version = 1
    name = "examples.MyAnalyzer"
    description = "Tries to fix misspelled identifiers."
    _log = logging.getLogger("ExamplesAnalyzer")

    @with_changed_uasts_and_contents
    def analyze(self, ptr_from: ReferencePointer, ptr_to: ReferencePointer,  # noqa: D
                data_service: DataService, changes: Iterable[Change]) -> [Comment]:
        self._log.info("analyze %s %s", ptr_from.commit, ptr_to.commit)
        comments = []
        for change in changes:
            comment = Comment()
            comment.file = change.head.path
            comment.text = "%s %d > %d" % (change.head.language,
                                           self.model.node_counts.get(change.base.path, 0),
                                           self.count_nodes(change.head.uast))
            comment.line = 0
            comment.confidence = 100
            comments.append(comment)
        return comments

    @classmethod
    @with_uasts_and_contents
    def train(cls, ptr: ReferencePointer, config: Dict[str, Any], data_service: DataService,  # noqa: D
              files: Iterable[File]) -> AnalyzerModel:
        cls._log.info("train %s %s", ptr.url, ptr.commit)
        model = cls.construct_model(ptr)
        model.node_counts = {}
        for file in files:
            model.node_counts[file.path] = cls.count_nodes(file.uast)
        return model

    @staticmethod
    def count_nodes(uast: Node):  # noqa
        stack = [uast]
        count = 0
        while stack:
            node = stack.pop()
            count += 1
            stack.extend(node.children)
        return count


analyzer_class = MyAnalyzer
