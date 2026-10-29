"""Static checks and sandboxed evaluation for submitted Python source.

Defense in depth, not a security boundary on the local backend: submissions run
in a separate interpreter with an empty environment, resource limits, restricted
builtins, and a whitelist-only import hook. Use the Docker backend when the
model's code must be confined.
"""
import ast
import json
import math
import subprocess
import sys

ALLOWED_MODULES = ("math", "itertools", "functools", "collections", "re",
                   "bisect", "heapq", "fractions", "statistics", "datetime")
# Names that reach the interpreter, the filesystem, or object internals.
BANNED_NAMES = {"eval", "exec", "compile", "open", "input", "globals", "locals", "vars",
                "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "memoryview",
                "type", "object", "super", "classmethod", "staticmethod", "property"}
# str.format and attrgetter walk attributes by string, which would bypass the
# double-underscore rule; the rest expose frames, modules, or the loader.
BANNED_ATTRIBUTES = {"format", "format_map", "attrgetter", "methodcaller", "sys", "modules",
                     "os", "subprocess", "builtins", "system", "popen", "importlib", "mro",
                     "gi_frame", "gi_code", "cr_frame", "ag_frame", "f_globals", "f_locals",
                     "f_builtins", "f_back", "tb_frame", "tb_next"}
SAFE_BUILTINS = ("abs", "all", "any", "bin", "bool", "bytes", "callable", "chr", "complex",
                 "dict", "divmod", "enumerate", "filter", "float", "format", "frozenset",
                 "hex", "int", "isinstance", "iter", "len", "list", "map", "max", "min",
                 "next", "oct", "ord", "pow", "range", "repr", "reversed", "round", "set",
                 "slice", "sorted", "str", "sum", "tuple", "zip", "ArithmeticError",
                 "AssertionError", "Exception", "IndexError", "KeyError", "OverflowError",
                 "StopIteration", "TypeError", "ValueError", "ZeroDivisionError")
CASE_SECONDS = 2
MAX_OUTPUT_CHARS = 100_000

WORKER = r'''
import builtins as _b
import json
import signal
import sys

request = json.loads(sys.stdin.read())
seconds = request["case_seconds"]
total = int(seconds * (len(request["cases"]) + 1)) + 2
try:
    import resource
except ImportError:
    resource = None
if resource is not None:
    for name, limit in (("RLIMIT_CPU", total), ("RLIMIT_FSIZE", 0), ("RLIMIT_CORE", 0),
                        ("RLIMIT_AS", 2 << 30)):
        try:
            resource.setrlimit(getattr(resource, name), (limit, limit))
        except (AttributeError, ValueError, OSError):
            pass


class Timeout(BaseException):
    pass


def on_alarm(signum, frame):
    raise Timeout()


signal.signal(signal.SIGALRM, on_alarm)


def timed(function, *args):
    signal.setitimer(signal.ITIMER_REAL, seconds, 0.05)
    try:
        return function(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


allowed = set(request["allowed"])
real_import = _b.__import__


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0 or name.split(".")[0] not in allowed:
        raise ImportError("import of " + name + " is not allowed")
    return real_import(name, globals, locals, fromlist, level)


safe = {name: getattr(_b, name) for name in request["builtins"]}
safe["__import__"] = safe_import
safe["print"] = lambda *args, **kwargs: None
namespace = {"__builtins__": safe, "__name__": "submission"}
out = sys.__stdout__
load_error = None
function = None
try:
    timed(exec, compile(request["source"], "<submission>", "exec"), namespace)
    function = namespace["f"]
except Timeout:
    load_error = "Timeout"
except BaseException as error:
    load_error = type(error).__name__
for args in request["cases"]:
    if load_error is not None:
        result = {"ok": False, "error": load_error}
    else:
        try:
            text = json.dumps(timed(function, *args), allow_nan=False)
            if len(text) > request["max_output"]:
                raise OverflowError("output too large")
            result = {"ok": True, "value": json.loads(text)}
        except Timeout:
            result = {"ok": False, "error": "Timeout"}
        except BaseException as error:
            result = {"ok": False, "error": type(error).__name__}
    out.write(json.dumps(result) + "\n")
    out.flush()
'''


def check_source(source, arity):
    """Reject source that cannot be a valid submission; raises ValueError with the reason."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ValueError(f"Syntax error on line {error.lineno}: {error.msg}") from None
    target = next((node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == "f"), None)
    if target is None:
        raise ValueError("Define a top-level function named f")
    spec = target.args
    if spec.vararg or spec.kwarg or spec.kwonlyargs or len(spec.posonlyargs) + len(spec.args) != arity:
        raise ValueError(f"f must take exactly {arity} positional parameter(s), "
                         "with no *args, **kwargs, or keyword-only parameters")
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await)):
            raise ValueError(f"Line {line}: classes and async code are not allowed")
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""] if node.level == 0 else [""]
        else:
            modules = []
        for module in modules:
            if module.split(".")[0] not in ALLOWED_MODULES:
                raise ValueError(f"Line {line}: import of '{module}' is not allowed; "
                                 f"allowed modules: {', '.join(ALLOWED_MODULES)}")
        if isinstance(node, ast.Name) and (node.id in BANNED_NAMES or "__" in node.id):
            raise ValueError(f"Line {line}: the name '{node.id}' is not allowed")
        if isinstance(node, ast.Attribute) and (node.attr in BANNED_ATTRIBUTES or "__" in node.attr):
            raise ValueError(f"Line {line}: the attribute '{node.attr}' is not allowed")
        if isinstance(node, (ast.arg, ast.keyword)):
            name = node.arg or ""
            if "__" in name:
                raise ValueError(f"Line {line}: the name '{name}' is not allowed")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise ValueError(f"Line {line}: strings containing a double underscore are not allowed")


def run_cases(source, cases):
    """Run f(*args) for every argument list in one sandboxed interpreter.

    Returns one {"ok": True, "value": ...} or {"ok": False, "error": name} per case;
    cases the worker never reached (it crashed or ran out of time) are errors.
    """
    payload = json.dumps({"source": source, "cases": cases, "case_seconds": CASE_SECONDS,
                          "allowed": list(ALLOWED_MODULES), "builtins": list(SAFE_BUILTINS),
                          "max_output": MAX_OUTPUT_CHARS})
    missing = "WorkerStopped"
    try:
        done = subprocess.run([sys.executable, "-I", "-S", "-c", WORKER], input=payload,
                              capture_output=True, text=True, env={},
                              timeout=CASE_SECONDS * (len(cases) + 1) + 5)
        stdout = done.stdout
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        missing = "Timeout"
    results = []
    for line in stdout.splitlines():
        try:
            results.append(json.loads(line))
        except ValueError:
            break
    results = results[:len(cases)]
    return results + [{"ok": False, "error": missing}] * (len(cases) - len(results))


def matches(expected, actual, tolerance=None):
    """Compare JSON values; bool is not int, and 3 equals 3.0 (or within tolerance)."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return isinstance(expected, bool) and isinstance(actual, bool) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if tolerance:
            return math.isclose(expected, actual, rel_tol=tolerance, abs_tol=tolerance)
        return expected == actual
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(expected) == len(actual)
                and all(matches(a, b, tolerance) for a, b in zip(expected, actual)))
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and expected.keys() == actual.keys()
                and all(matches(expected[key], actual[key], tolerance) for key in expected))
    return type(expected) is type(actual) and expected == actual
