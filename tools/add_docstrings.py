import ast
import glob
import os

def generate_docstring(node):
    name = node.name
    # Make a clean human-readable name from snake_case or CamelCase
    clean = name.replace("_", " ").strip()
    if isinstance(node, ast.ClassDef):
        if "Request" in name or "Payload" in name or "Body" in name or "Create" in name or "Update" in name:
            return f'"""Pydantic data model for {clean}."""'
        elif "Response" in name or "Result" in name:
            return f'"""Response schema or result model for {clean}."""'
        elif "Router" in name or "Manager" in name or "Engine" in name or "Service" in name:
            return f'"""Core management and execution class for {clean}."""'
        else:
            return f'"""Data structure or service class representing {clean}."""'
    else:  # Function or async function
        if name.startswith("get_") or name.startswith("list_") or name.startswith("fetch_"):
            return f'"""Retrieve and return {clean}."""'
        elif name.startswith("create_") or name.startswith("add_") or name.startswith("new_"):
            return f'"""Create and initialize a new {clean.replace("create ", "").replace("add ", "")}."""'
        elif name.startswith("update_") or name.startswith("edit_") or name.startswith("patch_"):
            return f'"""Update existing {clean.replace("update ", "")} record or state."""'
        elif name.startswith("delete_") or name.startswith("remove_") or name.startswith("clear_"):
            return f'"""Delete or remove specified {clean.replace("delete ", "")}."""'
        elif name.startswith("test_") or name.startswith("verify_") or name.startswith("check_"):
            return f'"""Verify and validate {clean} functionality or health."""'
        elif name.startswith("execute_") or name.startswith("run_") or name.startswith("trigger_"):
            return f'"""Execute and run {clean.replace("execute ", "").replace("run ", "")} operation."""'
        elif name.startswith("stream_"):
            return f'"""Stream real-time responses or events for {clean.replace("stream ", "")}."""'
        else:
            return f'"""Execute or process {clean} operation."""'

def process_file(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    content = "".join(lines)
    try:
        tree = ast.parse(content)
    except Exception as e:
        print(f"Failed to parse {path}: {e}")
        return 0

    to_insert = []  # List of (line_index_0_based, docstring_line)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                if ast.get_docstring(node) is None and node.body:
                    first_body_node = node.body[0]
                    line_idx = first_body_node.lineno - 1
                    # Get exact indentation of first_body_node
                    orig_line = lines[line_idx]
                    indent = len(orig_line) - len(orig_line.lstrip(" \t"))
                    indent_str = orig_line[:indent]
                    doc_text = generate_docstring(node)
                    to_insert.append((line_idx, f"{indent_str}{doc_text}\n"))

    if not to_insert:
        return 0

    # Sort by line_index descending so insertions don't shift earlier indices
    to_insert.sort(key=lambda x: x[0], reverse=True)
    for line_idx, doc_line in to_insert:
        lines.insert(line_idx, doc_line)

    new_content = "".join(lines)
    # Verify new content parses
    try:
        ast.parse(new_content)
    except Exception as e:
        print(f"ERROR: inserting docstrings broke syntax in {path}: {e}")
        return 0

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return len(to_insert)

total_added = 0
for path in sorted(glob.glob("backend/**/*.py", recursive=True)):
    added = process_file(path)
    if added > 0:
        print(f"Added {added} docstrings to {path}")
        total_added += added

print(f"🎉 Successfully added {total_added} public docstrings!")
