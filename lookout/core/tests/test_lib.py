import os
from tempfile import NamedTemporaryFile
import unittest

from bblfsh import BblfshClient, Node, Position

from lookout.core.api.service_data_pb2 import File
from lookout.core.lib import extract_changed_nodes, files_by_language, \
    filter_files_by_line_length, find_deleted_lines, find_new_lines, parse_files


class LibTests(unittest.TestCase):
    def test_find_deleted_lines(self):
        text_base = """
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        Maecenas volutpat dui id ipsum cursus, sit amet accumsan nisl ornare.
        Vivamus euismod lorem viverra semper dictum.
        Nam consectetur enim eget elementum mattis.
        Ut condimentum metus vehicula tellus tempus, vel ultricies lectus dapibus.
        Etiam vitae nisi at ante pretium lacinia et eu massa."""
        base_lines_number = text_base.count("\n") + 1
        # Delete first line
        new_line_indices = find_deleted_lines(
            File(content=bytes(text_base, "utf-8")),
            File(content=bytes("\n".join(text_base.split("\n")[1:]), "utf-8")))
        self.assertEqual(new_line_indices, [1])
        # Delete first two lines
        new_line_indices = find_deleted_lines(
            File(content=bytes(text_base, "utf-8")),
            File(content=bytes("\n".join(text_base.split("\n")[2:]), "utf-8")))
        self.assertEqual(new_line_indices, [1])
        # Delete last line
        new_line_indices = find_deleted_lines(
            File(content=bytes(text_base, "utf-8")),
            File(content=bytes("\n".join(text_base.split("\n")[:-1]), "utf-8")))
        self.assertEqual(new_line_indices, [base_lines_number - 1])
        # Delete last two lines
        new_line_indices = find_deleted_lines(
            File(content=bytes(text_base, "utf-8")),
            File(content=bytes("\n".join(text_base.split("\n")[:-2]), "utf-8")))
        self.assertEqual(new_line_indices, [base_lines_number - 2])
        # Delete line in the middle
        middle = 3
        text_head = text_base.split("\n")
        text_head.pop(middle)
        text_head = "\n".join(text_head)
        new_line_indices = find_deleted_lines(
            File(content=bytes(text_base, "utf-8")),
            File(content=bytes(text_head, "utf-8")))
        self.assertEqual(new_line_indices, [middle, middle + 1])

    def test_find_modified_lines(self):
        text_base = """
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        Maecenas volutpat dui id ipsum cursus, sit amet accumsan nisl ornare.
        Vivamus euismod lorem viverra semper dictum.
        Nam consectetur enim eget elementum mattis.
        Ut condimentum metus vehicula tellus tempus, vel ultricies lectus dapibus.
        Etiam vitae nisi at ante pretium lacinia et eu massa."""
        # inserted lines: 3 and 6 (counting from 1 with a new line at the start)
        # modified line: 4
        text_head = """
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        Curabitur congue libero vitae quam venenatis, tristique commodo diam lacinia.
        Mecenas volutpat dui id ipsum cursus, sit amet accumsan nisl ornare.
        Vivamus euismod lorem viverra semper dictum.
        Praesent eu ipsum sit amet elit aliquam laoreet.
        Nam consectetur enim eget elementum mattis.
        Ut condimentum metus vehicula tellus tempus, vel ultricies lectus dapibus.
        Etiam vitae nisi at ante pretium lacinia et eu massa."""
        new_line_indices = find_new_lines(File(content=bytes(text_base, "utf-8")),
                                          File(content=bytes(text_head, "utf-8")))
        self.assertEqual(new_line_indices, [3, 4, 6])

    def test_files_by_language(self):
        file_stats = {"js": 2, "Python": 5, "ruby": 7}
        files = []
        for language, n_files in file_stats.items():
            for i in range(n_files):
                files.append(File(language=language, uast=Node(children=[Node()]), path=str(i)))
        result = files_by_language(files)
        self.assertEqual({"js": 2, "python": 5, "ruby": 7}, {k: len(v) for k, v in result.items()})
        return result

    def test_files_by_line_length(self):
        filepath1 = os.path.join(os.path.dirname(__file__), "test_data_requests.py")
        filepath2 = os.path.join(os.path.dirname(__file__), "__init__.py")
        filtered = filter_files_by_line_length([filepath1, filepath2], 50)
        self.assertEqual(len(filtered), 1)

    def test_parse_files(self):

        class Log:
            def debug(self, *args, **kwargs):
                nonlocal logged
                logged = True

        logged = False
        with NamedTemporaryFile(prefix="one", suffix=".js") as tmp1:
            tmp1.write(b"hello")
            tmp1.seek(0)
            with NamedTemporaryFile(prefix="two", suffix=".js") as tmp2:
                tmp2.write(b"world" * 100)
                tmp2.seek(0)
            try:
                bblfsh_client = BblfshClient("0.0.0.0:9432")
                filtered = parse_files(filepaths=[tmp1.name, tmp2.name], line_length_limit=80,
                                       overall_size_limit=5 << 20, client=bblfsh_client,
                                       language="javascript", log=Log())
                self.assertEqual(len(filtered), 1)
                self.assertEqual(filtered[0].content, b"hello")
                self.assertTrue(logged)
            finally:
                bblfsh_client._channel.close()

    def test_extract_changed_nodes(self):
        root = Node(
            start_position=Position(line=10),
            children=[Node(start_position=Position(line=5))])
        nodes = extract_changed_nodes(root, [10])
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].start_position.line, 10)


if __name__ == "__main__":
    unittest.main()
