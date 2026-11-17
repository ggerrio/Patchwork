"""Tree-sitter Python AST chunker for extracting top-level functions and classes."""

from dataclasses import dataclass
from typing import Literal

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

_PY_LANGUAGE = Language(tspython.language())


@dataclass(frozen=True)
class CodeChunkItem:
    """Represents a top-level Python function or class extracted from source code."""

    file_path: str
    symbol_name: str
    chunk_type: Literal["function", "class"]
    start_line: int
    end_line: int
    content: str


def _extract_definition(
    node: Node,
    source_bytes: bytes,
    file_path: str,
) -> CodeChunkItem | None:
    """Extract a `CodeChunkItem` from a top-level definition or decorated definition."""
    target = node
    if node.type == "decorated_definition":
        inner = node.child_by_field_name("definition")
        if inner is None:
            for child in node.children:
                if child.type in {"function_definition", "class_definition"}:
                    inner = child
                    break
        if inner is None:
            return None
        target = inner

    if target.type == "function_definition":
        chunk_type: Literal["function", "class"] = "function"
    elif target.type == "class_definition":
        chunk_type = "class"
    else:
        return None

    name_node = target.child_by_field_name("name")
    symbol_name = (
        source_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8")
        if name_node is not None
        else "<anonymous>"
    )

    content = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
    return CodeChunkItem(
        file_path=file_path,
        symbol_name=symbol_name,
        chunk_type=chunk_type,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        content=content,
    )


def chunk_python_source(source: str, file_path: str = "<string>") -> list[CodeChunkItem]:
    """Parse Python source code with tree-sitter and extract top-level functions and classes."""
    if not source.strip():
        return []

    parser = Parser(_PY_LANGUAGE)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)

    chunks: list[CodeChunkItem] = []
    for child in tree.root_node.children:
        if child.type in {"function_definition", "class_definition", "decorated_definition"}:
            item = _extract_definition(child, source_bytes, file_path)
            if item is not None:
                chunks.append(item)

    return chunks
