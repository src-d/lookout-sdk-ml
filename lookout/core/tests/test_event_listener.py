import os
import unittest

from lookout.core.api.event_pb2 import PushEvent, ReviewEvent
from lookout.core.api.service_analyzer_pb2 import EventResponse
from lookout.core.event_listener import EventHandlers, EventListener
from lookout.core.test_helpers import server


class Handlers(EventHandlers):
    def __init__(self):
        self.request = None

    def process_review_event(self, request: ReviewEvent) -> EventResponse:
        self.request = request
        return EventResponse()

    def process_push_event(self, request: PushEvent) -> EventResponse:
        self.request = request
        return EventResponse()


class EventListenerTests(unittest.TestCase):
    COMMIT_FROM = "3ac2a59275902f7252404d26680e30cc41efb837"
    COMMIT_TO = "dce7fcba3d2151a0d5dc4b3a89cfc0911c96cf2b"

    def setUp(self):
        self.handlers = Handlers()
        self.port = server.find_port()

    def test_review(self):
        listener = EventListener("localhost:%d" % self.port, self.handlers).start()
        server.run("review", self.COMMIT_FROM, self.COMMIT_TO, self.port,
                   git_dir=os.getenv("LOOKOUT_SDK_ML_TESTS_GIT_DIR", "."))
        self.assertIsInstance(self.handlers.request, ReviewEvent)
        del listener

    def test_push(self):
        listener = EventListener("localhost:%d" % self.port, self.handlers).start()
        server.run("push", self.COMMIT_FROM, self.COMMIT_TO, self.port,
                   git_dir=os.getenv("LOOKOUT_SDK_ML_TESTS_GIT_DIR", "."))
        self.assertIsInstance(self.handlers.request, PushEvent)
        del listener


if __name__ == "__main__":
    unittest.main()
