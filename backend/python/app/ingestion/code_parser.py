import ast
import re
import io
import tokenize
from pathlib import PurePosixPath


CODE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".sh", ".sql", ".mjs"}


def module_name(filename):
    parts = PurePosixPath(filename.replace("\\", "/")).parts
    if "src" in parts:
        parts = parts[parts.index("src") + 1:]
    path = str(PurePosixPath(*parts))
    path = str(PurePosixPath(path).with_suffix("")).replace("/", ".")
    return path.removesuffix(".__init__")


def python_structure(text, filename):
    tree = ast.parse(text, filename=filename)
    if not text.strip():
        return {"entities": [], "relationships": [], "prose": [], "parser": "python_ast", "module": module_name(filename)}
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    module = module_name(filename)
    entities = {}
    relations = []
    aliases = {}
    definitions = {}

    def span(node):
        line = lines[node.lineno - 1]
        start = offsets[node.lineno - 1] + len(line.encode("utf-8")[:node.col_offset].decode("utf-8"))
        last = lines[node.end_lineno - 1]
        end = offsets[node.end_lineno - 1] + len(last.encode("utf-8")[:node.end_col_offset].decode("utf-8"))
        return start, end

    def entity(name, kind, start, end, context=False):
        key = kind + ":" + name
        occurrence = {"start": start, "end": end, "quote": text[start:end], "contextFromFilename": context}
        record = entities.setdefault(key, {"key": key, "name": name, "type": kind, **occurrence, "occurrences": []})
        if occurrence not in record["occurrences"]:
            record["occurrences"].append(occurrence)
        return key

    def relation(subject, predicate, target, start, end, resolution="syntax"):
        relations.append({"subject": subject, "predicate": predicate, "object": target, "start": start, "end": end, "quote": text[start:end], "resolution": resolution})

    first = next((node for node in tree.body if hasattr(node, "lineno")), None)
    left, right = span(first) if first is not None else (0, len(text.splitlines()[0]))
    root = entity(module, "code_module", left, min(right, text.find("\n", left) if "\n" in text[left:right] else right), True)

    class Definitions(ast.NodeVisitor):
        scope = []
        def visit_ClassDef(self, node):
            self.define(node)
        def visit_FunctionDef(self, node):
            self.define(node)
        visit_AsyncFunctionDef = visit_FunctionDef
        def define(self, node):
            qualified = ".".join([module, *self.scope, node.name])
            definitions[tuple([*self.scope, node.name])] = qualified
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()
    Definitions().visit(tree)

    class Structure(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
            self.parents = [root]
            self.class_scope = None

        def resolve(self, value):
            head, *tail = value.split(".")
            if head in aliases:
                return ".".join([aliases[head], *tail]), "import_name"
            if head in {"self", "cls"} and self.class_scope and tail:
                return ".".join([module, *self.class_scope, *tail]), "class_member_name"
            for size in range(len(self.scope), -1, -1):
                found = definitions.get(tuple(self.scope[:size] + [head]))
                if found:
                    return ".".join([found, *tail]), "local_name"
            return module + "::" + value, "unresolved_name"

        def visit_Import(self, node):
            start, end = span(node)
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = item.name if item.asname else item.name.split(".")[0]
                left, right = span(item)
                target = entity(item.name, "code_module", left, right)
                relation(root, "imports", target, left, right)

        def visit_ImportFrom(self, node):
            start, end = span(node)
            package = module.split(".") if filename.endswith("__init__.py") else module.split(".")[:-1]
            prefix = ".".join(package[:len(package) - node.level + 1]) if node.level else ""
            imported = ".".join(part for part in (prefix, node.module) if part)
            prefix_end = start + re.search(r'\bimport\b', text[start:end]).end()
            target = entity(imported or module, "code_module", start, prefix_end)
            relation(root, "imports", target, start, prefix_end)
            for item in node.names:
                qualified = ".".join(part for part in (imported, item.name) if part)
                aliases[item.asname or item.name] = qualified
                if item.name != "*":
                    left, right = span(item)
                    symbol = entity(qualified, "code_symbol", left, right)
                    relation(root, "imports_symbol", symbol, left, right)

        def visit_ClassDef(self, node):
            self.define(node, True)
        def visit_FunctionDef(self, node):
            self.define(node, False)
        visit_AsyncFunctionDef = visit_FunctionDef

        def define(self, node, is_class):
            start, end = span(node)
            header_end = text.find("\n", start)
            header_end = min(end, header_end if header_end >= 0 else end)
            header = text[start:header_end]
            match = re.search(r"\b" + re.escape(node.name) + r"\b", header)
            name_start = start + match.start() if match else start
            qualified = ".".join([module, *self.scope, node.name])
            target = entity(qualified, "code_symbol", name_start, name_start + len(node.name))
            relation(self.parents[-1], "defines", target, start, name_start + len(node.name))
            if is_class:
                for base in node.bases:
                    base_start, base_end = span(base)
                    name, resolution = self.resolve(ast.unparse(base))
                    parent = entity(name, "code_symbol", base_start, base_end)
                    relation(target, "inherits_from", parent, base_start, base_end, resolution)
            previous_class = self.class_scope
            self.scope.append(node.name)
            if is_class:
                self.class_scope = list(self.scope)
            self.parents.append(target)
            self.generic_visit(node)
            self.parents.pop()
            self.scope.pop()
            self.class_scope = previous_class

        def visit_Call(self, node):
            start, end = span(node.func)
            value = text[start:end]
            if value and isinstance(node.func, (ast.Name, ast.Attribute)):
                name, resolution = self.resolve(value)
                target = entity(name, "code_symbol", start, end)
                relation(self.parents[-1], "calls", target, start, end, resolution)
            self.generic_visit(node)

    Structure().visit(tree)
    prose = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            start, end = span(node.body[0])
            prose.append({"start": start, "end": end, "kind": "docstring"})
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            prose.append({"start": offsets[token.start[0] - 1] + token.start[1], "end": offsets[token.end[0] - 1] + token.end[1], "kind": "comment"})
    return {"entities": list(entities.values()), "relationships": relations, "prose": prose, "parser": "python_ast", "module": module, "meaning": "Syntax relationships; unresolved call names are not runtime target resolution"}
