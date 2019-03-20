import lzma
import os
import unittest

import bblfsh
from lookout.sdk.service_data_pb2 import File
import numpy

from lookout.core.bytes_to_unicode_converter import BytesToUnicodeConverter


def check_uast_transformation(test_case: unittest.TestCase, content: bytes,
                              uast_byte_positions, uast_unicode_positions):
    for node_byte, node_uni in zip(BytesToUnicodeConverter._traverse_uast(uast_byte_positions),
                                   BytesToUnicodeConverter._traverse_uast(uast_unicode_positions)):
        if (node_byte.start_position != node_uni.start_position or
                node_byte.end_position != node_uni.end_position):
            test_case.assertEqual(
                len(content[node_byte.start_position.offset:
                            node_byte.end_position.offset].decode(errors="replace")),
                node_uni.end_position.offset - node_uni.start_position.offset)


class BytesToUnicodeConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parse = bblfsh.BblfshClient("localhost:9432").parse

    def test_build_bytes_to_str_offset_mapping(self):
        content = "I don't take an apéritif après-ski".encode() + \
                  b"\x80\x80\xb3\x09\xc3\xa8\x80\x80\xc3\x80"
        content_str = content.decode(errors="replace")
        byte_to_str_offset = BytesToUnicodeConverter._build_bytes_to_str_offset_mapping(content)
        for offset_byte, offset_str in byte_to_str_offset.items():
            self.assertEqual(content[:offset_byte].decode(errors="replace"),
                             content_str[:offset_str])
            self.assertEqual(content[offset_byte:].decode(errors="replace"),
                             content_str[offset_str:])

    def test_byte_eq_str(self):
        code = b"var a = 1;\nvar b = 'abc'"
        response = self.parse(contents=code, language="javascript", filename="test.js")
        uast = response.uast

        converter = BytesToUnicodeConverter(code)
        uast2 = converter.convert_uast(uast)
        self.assertEqual(uast, uast2)

    def test_byte_not_eq_str(self):
        code = b"var a = 1;\nvar b = '\xc3\x80'"
        response = self.parse(contents=code, language="javascript", filename="test.js")
        uast = response.uast

        converter = BytesToUnicodeConverter(code)
        uast_uni = converter.convert_uast(uast)
        check_uast_transformation(self, code, uast, uast_uni)

    def test_build_lines_offset_mapping(self):
        content = "1\n23\n\n456\r\n\t\t\t\n\n"
        res = BytesToUnicodeConverter._build_lines_offset_mapping(content)
        self.assertTrue((res == numpy.array([0,  2,  5,  6, 11, 15, 17])).all())

    def test_convert_file(self):
        code = b"var a = 1;\nvar b = '\xc3\x80'"
        response = self.parse(contents=code, language="javascript", filename="test.js")
        uast = response.uast

        file = File(content=code, path="test.js", language="javascript", uast=uast)
        unicode_file = BytesToUnicodeConverter.convert_file(file)
        self.assertEqual(unicode_file.content, code.decode())
        self.assertEqual(unicode_file.path, file.path)
        self.assertEqual(unicode_file.language, file.language)
        check_uast_transformation(self, code, uast, unicode_file.uast)

    def test_real_file(self):
        filepath = os.path.join(os.path.split(__file__)[0], "test-markdown-options.js.xz")
        with lzma.open(filepath) as f:
            content = f.read()
        uast = self.parse(contents=content, filename=filepath, language="javascript").uast
        uast_uni = BytesToUnicodeConverter(content).convert_uast(uast)
        check_uast_transformation(self, content, uast, uast_uni)


if __name__ == "__main__":
    unittest.main()
