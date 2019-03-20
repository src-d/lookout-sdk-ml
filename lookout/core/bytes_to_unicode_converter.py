from typing import Dict, Iterator

import bblfsh
from lookout.sdk.service_data_pb2 import Change, File
import numpy

from lookout.core.analyzer import UnicodeChange, UnicodeFile


class BytesToUnicodeConverter:
    """Utility class to convert bytes positions to unicode positions in `bblfsh.Node`."""

    def __init__(self, content: bytes):
        """
        Initialize a new instance of BytesToUnicodeConverter.

        :param content: Code byte representation.
        """
        self._content = content
        self._content_str = content.decode(errors="replace")
        self._lines = self._content_str.splitlines(keepends=True)
        self._byte_to_str_offset = self._build_bytes_to_str_offset_mapping(content)
        self._lines_offset = self._build_lines_offset_mapping(self._content_str)

    def convert_content(self):
        """Convert byte content (or code) to unicode."""
        return self._content_str

    def convert_uast(self, uast: bblfsh.Node) -> bblfsh.Node:
        """
        Convert uast Nodes bytes position to unicode position.

        UAST is expected to correspond to provided content.
        :param uast: corresponding UAST.
        :return: UAST with unicode positions.
        """
        uast = bblfsh.Node.FromString(uast.SerializeToString())  # deep copy the whole tree
        if not self._content:
            return uast
        for node in self._traverse_uast(uast):
            for position in (node.start_position, node.end_position):
                if position.offset == 0 and position.col == 0 and position.line == 0:
                    continue
                new_position = self._convert_position(position)
                for attr in ("offset", "line", "col"):
                    setattr(position, attr, getattr(new_position, attr))
        return uast

    @staticmethod
    def convert_file(file: File) -> UnicodeFile:
        """
        Convert lookout `File` to `UnicodeFile` with converted content and uast.

        path and language fields are the same for result and provided `File` instance.

        :param file: lookout File to convert.
        :return: New UnicodeFile instance.
        """
        converter = BytesToUnicodeConverter(file.content)
        return UnicodeFile(
            content=converter.convert_content(),
            uast=converter.convert_uast(file.uast),
            path=file.path,
            language=file.language,
        )

    @staticmethod
    def convert_change(change: Change) -> UnicodeChange:
        """
        Convert lookout `Change` to `UnicodeChange` with converted content and uast.

        :param change: lookout Change to convert.
        :return: New UnicodeChange instance.
        """
        return UnicodeChange(
            base=BytesToUnicodeConverter.convert_file(change.base),
            head=BytesToUnicodeConverter.convert_file(change.head),
        )

    def _convert_position(self, byte_position: bblfsh.Position) -> bblfsh.Position:
        """Get a new byte_position from an old one."""
        offset = self._byte_to_str_offset[byte_position.offset]
        line_num = numpy.argmax(self._lines_offset > offset) - 1
        col = offset - self._lines_offset[line_num]
        # line number can change. File example:
        # github.com/src-d/style-analyzer/blob/ed9324d783eb0082d2f59de336190c8805a33c75/lookout/style/format/tests/bugs/002_bad_line_positions/browser-policy-content.js
        line = self._lines[line_num]
        if len(line) == col:
            if line.splitlines()[0] != line:
                # ends with newline
                line_num += 1
                col = 0
        assert line_num + 1 >= byte_position.line, \
            ("Unicode line number %d is smaller then in bytes (%d)."
                "position.") % (line_num + 1, byte_position.line)
        return bblfsh.Position(offset=offset, line=line_num + 1, col=col + 1)

    @staticmethod
    def _build_lines_offset_mapping(content: str) -> numpy.ndarray:
        """
        Create a dictionary with line number to bytes offset for the line start mapping.

        :param content: Code byte representation.
        :return: array with lines offsets. Last number is equal to the length of the content.
        """
        if not content:
            return numpy.empty(shape=(0, 0))
        line_start_offsets = [0]
        for d in content.splitlines(keepends=True):
            line_start_offsets.append(line_start_offsets[-1] + len(d))
        line_start_offsets[-1] += 1
        return numpy.array(line_start_offsets)

    @staticmethod
    def _build_bytes_to_str_offset_mapping(content: bytes) -> Dict[int, int]:
        """
        Create a dictionary with bytes offset to unicode string offset mapping.

        :param content: Bytes object which is used to create offsets mapping.
        :return: Dictionary with bytes offset to unicode string offset mapping.
        """
        byte_to_str_offset = {0: 0}
        byte_len_before = 0
        content_str = content.decode(errors="replace")
        for i, char in enumerate(content_str):
            if char != "\ufffd":  # replacement character
                byte_len_before += len(char.encode())
            else:
                byte_len_before += 1  # It is smart enough to replace by byte that is why only +=1
            byte_to_str_offset[byte_len_before] = i + 1
        byte_to_str_offset[len(content)] = len(content_str)
        return byte_to_str_offset

    @staticmethod
    def _traverse_uast(uast: "bblfsh.Node") -> Iterator["bblfsh.Node"]:
        stack = [uast]
        while stack:
            node = stack.pop(0)
            stack.extend(node.children)
            yield node
