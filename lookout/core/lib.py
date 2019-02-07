"""Various utilities for analyzers to work with UASTs and plain texts."""
from collections import defaultdict
from difflib import SequenceMatcher
import logging
from os.path import isfile
import random
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from bblfsh import BblfshClient, Node
from bblfsh.client import NonUTF8ContentException

from lookout.core.api.service_data_pb2 import File
from lookout.core.garbage_exclusion import GARBAGE_PATTERN


def find_new_lines(before: File, after: File) -> List[int]:
    """
    Return the new line numbers from the pair of "before" and "after" files.

    :param before: The previous contents of the file.
    :param after: The new contents of the file.
    :return: List of line numbers new to `after`.
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

    :param before: The previous contents of the file.
    :param after: The new contents of the file.
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
    :return: List of UAST nodes which are suspected to have been changed.
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

    :param files: Iterable of `File`-s.
    :return: Dictionary with languages as keys and files mapped to paths as values.
    """
    result = defaultdict(dict)
    for file in files:
        if not len(file.uast.children):
            continue
        result[file.language.lower()][file.path] = file
    return result


def filter_files_by_path(filepaths: Iterable[str], exclude_pattern: Optional[str] = None,
                         ) -> Iterable[str]:
    """
    Filter out files by specific patterns in their path.

    :param filepaths: Iterable of file paths to examine.
    :param exclude_pattern: Regular expression to search in file paths. The matched files \
                            are excluded from the result. If it is None, we use the "garbage" \
                            pattern defined in lookout.core.langs. If it is an empty string, \
                            filtering is disabled.
    :return: List of paths, filtered.
    """
    passed = []
    if exclude_pattern is None:
        exclude_pattern = GARBAGE_PATTERN
    exclude_compiled_pattern = re.compile(exclude_pattern) if exclude_pattern else None
    for filepath in filepaths:
        if not isfile(filepath):
            continue
        if exclude_compiled_pattern and exclude_compiled_pattern.search(filepath):
            continue
        passed.append(filepath)
    return passed


def filter_files_by_line_length(filepaths: Iterable[str], line_length_limit: int) -> Iterable[str]:
    """
    Filter out files that have lines longer than `line_length_limit`.

    :param filepaths: Paths to the files to filter.
    :param line_length_limit: Maximum line length to accept a file. \
                              We measure the length in bytes, not in Unicode characters.
    :return: Files passed through the maximum line length filter.
    """
    line_passed = []
    for filepath in filepaths:
        with open(filepath, "rb") as f:
            content = f.read()
        if len(max(content.splitlines(), key=len, default=b"")) <= line_length_limit:
            line_passed.append(filepath)
    return line_passed


def parse_files(filepaths: Iterable[str], line_length_limit: int, overall_size_limit: int,
                client: BblfshClient, language: str, random_state: int = 7,
                progress_tracker: Callable = lambda x: x, log: Optional[logging.Logger] = None
                ) -> Iterable[File]:
    """
    Parse files with Babelfish.

    If a file has lines longer than `line_length_limit`, it is skipped. If the summed size of \
    parsed files exceeds `overall_size_limit` the rest of the files is skipped. Files paths are \
    filtered with `filter_files_by_path()`. The order in which the files are parsed is random - \
    and hence different from `filepaths`.

    :param filepaths: File paths to filter.
    :param line_length_limit: Maximum line length to accept a file.
    :param overall_size_limit: Maximum cumulative files size in bytes. \
                               The files are discarded after reaching this limit.
    :param client: Babelfish client instance. The Babelfish server should be running.
    :param language: Language to consider. Will discard the other languages.
    :param random_state: Random generator state for shuffling the files.
    :param progress_tracker: Optional progress metric whenn iterating over the input files.
    :param log: Logger to use to report the number of excluded files.
    :return: `File`-s with parsed UASTs and which passed through the filters.
    """
    random.seed(random_state)
    filepaths_filtered = filter_files_by_path(filepaths)
    files_filtered_by_line_length = filter_files_by_line_length(filepaths_filtered,
                                                                line_length_limit)
    files_filtered_by_line_length = random.sample(files_filtered_by_line_length,
                                                  k=len(files_filtered_by_line_length))
    size, n_parsed = 0, 0
    size_passed = []
    for filename in progress_tracker(files_filtered_by_line_length):
        try:
            res = client.parse(filename)
        except NonUTF8ContentException:
            # skip files that can't be parsed because of UTF-8 decoding errors.
            continue
        if res.status == 0 and res.language.lower() == language.lower():
            n_parsed += 1
            with open(filename, "rb") as f:
                content = f.read()
            size += len(content)
            if size > overall_size_limit:
                break
            uast = res.uast
            path = filename
            size_passed.append(File(content=content, uast=uast, path=path,
                                    language=res.language.lower()))
    if log is not None:
        log.debug("excluded %d/%d files based on their path",
                  len(filepaths) - len(filepaths_filtered), len(filepaths))
        log.debug("excluded %d/%d %s files by max line length %d",
                  len(filepaths_filtered) - len(files_filtered_by_line_length),
                  len(filepaths_filtered), language, line_length_limit)
        log.debug("excluded %d/%d %s files due to parsing problems",
                  len(files_filtered_by_line_length) - n_parsed,
                  len(files_filtered_by_line_length), language)
        log.debug("excluded %d/%d %s files by max overall size %d",
                  n_parsed - len(size_passed), n_parsed, language,
                  overall_size_limit)
    return size_passed
