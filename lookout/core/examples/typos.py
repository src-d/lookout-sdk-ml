from collections import defaultdict
import logging
from typing import Any, Dict, Iterable

import autocorrect
import bblfsh
from sourced.ml.algorithms import TokenParser, UastIds2Bag

from lookout.core.analyzer import Analyzer, AnalyzerModel, ReferencePointer
from lookout.core.api.service_analyzer_pb2 import Comment
from lookout.core.api.service_data_pb2 import Change, File
from lookout.core.data_requests import DataService, \
    with_changed_uasts_and_contents, with_uasts_and_contents
from lookout.core.lib import find_new_lines


class TyposModel(AnalyzerModel):  # noqa: D
    NAME = "typos"
    VENDOR = "source{d}"

    def __init__(self, **kwargs):
        """Declare names - the set of identifier parts occurred."""
        super().__init__(**kwargs)
        self.names = set()

    def _load_tree(self, tree: dict) -> None:
        self.names = tree["names"]

    def _generate_tree(self) -> dict:
        return {"names": self.names}


class TyposAnalyzer(Analyzer):  # noqa: D
    model_type = TyposModel
    version = 1
    name = "examples.TyposAnalyzer"
    description = "Reports the changes in UAST node counts."
    _log = logging.getLogger("TyposAnalyzer")

    @with_changed_uasts_and_contents
    def analyze(self, ptr_from: ReferencePointer, ptr_to: ReferencePointer,  # noqa: D
                data_service: DataService, changes: Iterable[Change]) -> [Comment]:
        self._log.info("analyze %s %s", ptr_from.commit, ptr_to.commit)
        comments = []
        parser = TokenParser(stem_threshold=100, single_shot=True)
        words = autocorrect.word.KNOWN_WORDS.copy()
        try:
            for name in self.model.names:
                if len(name) >= 3:
                    autocorrect.word.KNOWN_WORDS.add(name)
            for change in changes:
                suggestions = defaultdict(list)
                new_lines = set(find_new_lines(change.base, change.head))
                for node in bblfsh.filter(change.head.uast, "//*[@roleIdentifier]"):
                    if node.start_position is not None and node.start_position.line in new_lines:
                        for part in parser.split(node.token):
                            if part not in self.model.names:
                                fixed = autocorrect.spell(part)
                                if fixed != part:
                                    suggestions[node.start_position.line].append(
                                        (node.token, part, fixed))
                for line, s in suggestions.items():
                    comment = Comment()
                    comment.file = change.head.path
                    comment.text = "\n".join("`%s`: %s > %s" % fix for fix in s)
                    comment.line = line
                    comment.confidence = 100
                    comments.append(comment)
        finally:
            autocorrect.word.KNOWN_WORDS = words
        return comments

    @classmethod
    @with_uasts_and_contents
    def train(cls, ptr: ReferencePointer, config: Dict[str, Any], data_service: DataService,  # noqa: D
              files: Iterable[File]) -> AnalyzerModel:
        cls._log.info("train %s %s", ptr.url, ptr.commit)
        model = cls.construct_model(ptr)
        uast2ids = UastIds2Bag(token_parser=TokenParser(stem_threshold=100))
        for file in files:
            model.names.update(uast2ids(file.uast))
        cls._log.info("Parsed %d names", len(model.names))
        return model


analyzer_class = TyposAnalyzer
