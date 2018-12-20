"""Various utilities for analyzers to work with UASTs and plain texts."""
from collections import defaultdict
from difflib import SequenceMatcher
import logging
from os.path import isfile
import re
from typing import Dict, Iterable, List, Optional, Sequence

from bblfsh import BblfshClient, Node
from bblfsh.client import NonUTF8ContentException
from tqdm import tqdm

from lookout.core.api.service_data_pb2 import File
from lookout.core.garbage_exclusion import GARBAGE_PATTERN


def find_new_lines(before: File, after: File) -> List[int]:
    """
    Return the new line numbers from the pair of "before" and "after" files.

    :param before: the previous contents of the file.
    :param after: the new contents of the file.
    :return: list of line numbers new to `after`.
    """
    matcher = SequenceMatcher(a=before.content.decode("utf-8", "replace").splitlines(),
                              b=after.content.decode("utf-8", "replace").splitlines())
    result = []
    for action, _, _, j1, j2 in matcher.get_opcodes():
        if action in ("equal", "delete"):
            continue
        result.extend(range(j1 + 1, j2 + 1))
    return result


def find_deleted_lines(before: File, after: File) -> List[int]:
    """
    Return line numbers next to deleted lines in the new file.

    :param before: the previous contents of the file.
    :param after: the new contents of the file.
    :return: list of line numbers next to deleted lines.
    """
    before_lines = before.content.decode("utf-8", "replace").splitlines()
    after_lines = after.content.decode("utf-8", "replace").splitlines()
    matcher = SequenceMatcher(a=before_lines, b=after_lines)
    result = []
    for action, _, _, j1, _ in matcher.get_opcodes():
        if action == "delete":
            if j1 != 0:
                result.append(j1)
            if j1 != len(after_lines):
                result.append(j1 + 1)
    return result


def extract_changed_nodes(root: Node, lines: Sequence[int]) -> List[Node]:
    """
    Collect the list of UAST nodes which lie on the changed lines.

    :param root: UAST root node.
    :param lines: Changed lines, typically obtained via find_new_lines(). Empty list means all \
                  the lines.
    :return: list of UAST nodes which are suspected to have been changed.
    """
    lines = set(lines)
    queue = [root]
    result = []
    while queue:
        node = queue.pop()
        for child in node.children:
            queue.append(child)
        if not node.start_position:
            continue
        if not lines or node.start_position.line in lines:
            result.append(node)
    return result


def files_by_language(files: Iterable[File]) -> Dict[str, Dict[str, File]]:
    """
    Sorts files by programming language and path.

    :param files: iterable of `File`-s.
    :return: dictionary with languages as keys and files mapped to paths as values.
    """
    result = defaultdict(dict)
    for file in files:
        if not len(file.uast.children):
            continue
        result[file.language.lower()][file.path] = file
    return result


def filter_filepaths(filepaths: Iterable[str], exclude_pattern: Optional[str] = None,
                     ) -> Iterable[str]:
    """
    Mirror of the file filtering used in the format analyzer for use by debugging tools.

    :param filepaths: Iterable of filepaths to filter.
    :param exclude_pattern: Pattern to reject files based on their path. If None, uses the pattern
                            currently in use in lookout.core. Use "" to not filter anything.
    :return Iterable of paths, filtered.
    """
    if exclude_pattern is None:
        exclude_pattern = GARBAGE_PATTERN
    exclude_compiled_pattern = re.compile(exclude_pattern) if exclude_pattern else None
    for filepath in filepaths:
        if not isfile(filepath):
            continue
        if exclude_compiled_pattern and exclude_compiled_pattern.search(filepath):
            continue
        yield filepath


def filter_files(filenames: Iterable[str], line_length_limit: int, client: BblfshClient,
                 language: str, log: logging.Logger = None) -> Iterable[File]:
    """
    Filter files based on `language` and their maximum line length.

    :param filenames: paths to the files to filter.
    :param line_length_limit: maximum line length to accept a file.
    :param client: Babelfish client. Babelfish server should be started accordingly.
    :param language: Language to consider. Will discard the other languages.
    :param log: logger to use to report the number of excluded files.
    :return: files passed through the filter and the number of files which were excluded.
    """
    passed = []
    n_parsed = 0
    for filename in tqdm(filter_filepaths(filenames)):
        try:
            res = client.parse(filename)
        except NonUTF8ContentException:
            # skip files that can't be parsed because of UTF-8 decoding errors.
            continue
        if res.status == 0 and res.language.lower() == language.lower():
            uast = res.uast
            path = filename
            n_parsed += 1
            with open(filename) as f:
                content = f.read().encode("utf-8")
            if len(max(content.splitlines(), key=len, default=b"")) <= line_length_limit:
                passed.append(File(content=content, uast=uast, path=path,
                                   language=res.language.lower()))
    if log is not None:
        log.debug("excluded %d/%d %s files by max line length %d",
                  n_parsed - len(passed), n_parsed, language, line_length_limit)
    return passed
