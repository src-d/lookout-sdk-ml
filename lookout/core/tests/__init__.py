from lookout.core.test_helpers import server

if not server.exefile.exists():
    server.fetch()
