from __future__ import annotations

from pathlib import Path


PLAN_MARKER = "Plan:"


def comment_prefix(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp"}:
        return "//"
    return "#"


def build_pseudocode_comments(
    *,
    file_path: str,
    current_code: str,
    reference_code: str,
    invariant: str | None = None,
) -> dict[str, object]:
    prefix = comment_prefix(file_path)
    lines = _strip_legacy_check_comments(current_code.splitlines())
    if _already_has_comments(lines):
        content = _join_like(current_code, lines)
        return {"content": content, "comment_count": 0, "changed": content != current_code}

    reference_lines = reference_code.splitlines()
    output: list[str] = []
    inserted = 0
    pseudocode_inserted = False

    for index, line in enumerate(lines):
        if not pseudocode_inserted and _looks_like_function(line):
            block = _pseudocode_block(prefix, line, invariant)
            output.extend(block)
            inserted += len(block)
            pseudocode_inserted = True

        output.append(line)

    if not pseudocode_inserted:
        block = _pseudocode_block(prefix, "", invariant)
        output = [*block, *output]
        inserted += len(block)

    content = _join_like(current_code, output)
    return {"content": content, "comment_count": inserted, "changed": content != current_code}


def _looks_like_function(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("def ") or stripped.startswith("function ") or "=>" in stripped


def _pseudocode_block(prefix: str, function_line: str, invariant: str | None) -> list[str]:
    if invariant and "tenant" in invariant.lower():
        return [
            f"{prefix} {PLAN_MARKER} accept the input collection and the requested tenant.",
            f"{prefix} {PLAN_MARKER} keep only items that belong to that requested tenant.",
            f"{prefix} {PLAN_MARKER} return the filtered result without exposing other tenants' data.",
        ]
    return [
        f"{prefix} {PLAN_MARKER} preserve the behavior described by this check.",
        f"{prefix} {PLAN_MARKER} walk through the inputs, apply the invariant, then return the safe result.",
    ]


def _already_has_comments(lines: list[str]) -> bool:
    return any(PLAN_MARKER in line for line in lines)


def _strip_legacy_check_comments(lines: list[str]) -> list[str]:
    return [line for line in lines if "Check this line:" not in line]


def _join_like(original: str, lines: list[str]) -> str:
    content = "\n".join(lines)
    if original.endswith("\n"):
        content += "\n"
    return content
