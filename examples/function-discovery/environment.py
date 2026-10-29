"""Black-box function discovery: probe hidden functions, then submit an implementation.

All authoritative state stays in snapshots; reference implementations and hidden
tests are reloaded from functions.py and never enter an observation.
"""
from copy import deepcopy
import json
import math

import functions as library
import sandbox
from sdk import notify, progress, finish

MAX_BATCH = 20
MAX_NOTE = 4000
MAX_SOURCE = 8192
MISS_WARNINGS = 2
VIEW_LIMIT = 30 * 1024
DEFAULT_BOUND = 10**12
KINDS = ("int", "float", "str", "bool", "list[int]", "list[float]", "list[str]")
NULLABLE = " | null"
ERROR_MESSAGE_LIMIT = 200


def param_specs(fn):
    """Effective parameter specs: declared fields plus defaulted bounds."""
    specs = []
    for param in fn["params"]:
        kind = param["type"]
        spec = {"name": param["name"], "type": kind}
        if kind in ("int", "float", "list[int]", "list[float]"):
            spec["min"] = param.get("min", -DEFAULT_BOUND)
            spec["max"] = param.get("max", DEFAULT_BOUND)
        if kind == "str" or kind.startswith("list["):
            spec["max_len"] = param.get("max_len", 200 if kind == "str" else 50)
        if kind == "list[str]":
            spec["max_item_len"] = param.get("max_item_len", 50)
        specs.append(spec)
    return specs


def param_summary(spec):
    """One plain sentence fragment saying exactly which values a parameter accepts."""
    kind = spec["type"]
    if kind in ("int", "float"):
        return f"{kind}, {spec['min']} to {spec['max']}"
    if kind == "str":
        return f"string of at most {spec['max_len']} characters"
    if kind == "bool":
        return "true or false"
    if kind == "list[str]":
        return (f"list of at most {spec['max_len']} strings, "
                f"each at most {spec['max_item_len']} characters")
    return f"list of at most {spec['max_len']} {kind[5:-1]}s, each {spec['min']} to {spec['max']}"


def spent(rec):
    """Queries charged so far; a call on which the hidden function raised is free."""
    return sum("error" not in query for query in rec["queries"])


def signature(fn):
    shown = {"function": "f", "text": signature_text(fn),
             "params": [{**spec, "constraints": param_summary(spec)} for spec in param_specs(fn)],
             "returns": fn["returns"]}
    if fn.get("raises"):
        shown["raises"] = "Some inputs make the function raise an error."
    if fn.get("description"):
        shown["description"] = fn["description"]
    if fn.get("tolerance"):
        shown["tolerance"] = fn["tolerance"]
    return shown


def signature_text(fn):
    params = ", ".join(f"{p['name']}: {p['type']}" for p in fn["params"])
    return f"f({params}) -> {fn['returns']}"


def check_value(kind, spec, value, where, *, item=False):
    """Validate one argument against its spec; raises ValueError naming the problem."""
    if kind.startswith("list["):
        if not isinstance(value, list):
            raise ValueError(f"{where} must be a list")
        if len(value) > spec["max_len"]:
            raise ValueError(f"{where} has more than {spec['max_len']} items")
        for index, element in enumerate(value):
            check_value(kind[5:-1], spec, element, f"{where}[{index}]", item=True)
    elif kind in ("int", "float"):
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not number or (kind == "int" and not isinstance(value, int)):
            raise ValueError(f"{where} must be {'an int' if kind == 'int' else 'a number'}")
        if not math.isfinite(value) or not spec["min"] <= value <= spec["max"]:
            raise ValueError(f"{where} must be between {spec['min']} and {spec['max']}")
    elif kind == "str":
        if not isinstance(value, str):
            raise ValueError(f"{where} must be a string")
        limit = spec["max_item_len"] if item else spec["max_len"]
        if len(value) > limit:
            raise ValueError(f"{where} is longer than {limit} characters")
    elif kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{where} must be a boolean")


class FunctionDiscovery:
    # Log record schema (state["log"], append-only, private to the host and reports):
    #   {"seq": int, "type": "init" | "query" | "note" | "submit" | "missed_turn" | "finish",
    #    "function": function id or None, "label": "F1".. or None, "revision": int,
    #    "seat": acting seat or "environment", "outcome": "accepted" | "forfeited" | "warned", ...}
    #   query:  "calls": [args], "results": [{"output": v} | {"error": type, "message": text}],
    #           "queries_left": n (only calls that returned an output are charged)
    #   note:   "chars": n
    #   submit: "passed": n, "total": n, "case_results": [{"args", "expected", "actual", "error", "passed"}]
    # Rejected actions raise before mutating state, so they leave no record here.
    def initialize(self, params):
        seats = params["seats"]
        if len(seats) != 1:
            raise ValueError("Exactly one solver seat is required")
        config = {"query_budget": 20, "functions": [], "tiers": []}
        config.update(params.get("config", {}))
        registry = {fn["id"]: fn for fn in library.FUNCTIONS}
        if len(registry) != len(library.FUNCTIONS):
            raise ValueError("Function ids must be unique")
        unknown_tiers = [tier for tier in config["tiers"] if tier not in library.TIERS]
        if unknown_tiers:
            raise ValueError(f"Unknown tiers: {unknown_tiers}; choose from {list(library.TIERS)}")
        order = list(config["functions"]) or [fn["id"] for fn in library.FUNCTIONS]
        unknown = [fn_id for fn_id in order if fn_id not in registry]
        if unknown or len(set(order)) != len(order):
            raise ValueError(f"Invalid function selection: {unknown or order}")
        if config["tiers"]:
            order = [fn_id for fn_id in order if registry[fn_id]["tier"] in config["tiers"]]
        if not order:
            raise ValueError("The functions and tiers settings select no function")
        records = []
        for number, fn_id in enumerate(order, 1):
            fn = registry[fn_id]
            if not fn["tests"]:
                raise ValueError(f"Function {fn_id} has no tests")
            records.append({"id": fn_id, "label": f"F{number}",
                            "budget": fn.get("query_budget") or config["query_budget"],
                            "queries": [], "note": "", "submission": None, "passed": None,
                            "total": len(fn["tests"]), "case_results": None, "forfeited": False})
        self.state = {"seat": seats[0]["id"], "config": config, "records": records, "current": 0,
                      "revision": 0, "phase": "playing", "log": [], "seq": 0}
        self._log("init", None, seat="environment", outcome="accepted", order=order,
                  tiers=[registry[fn_id]["tier"] for fn_id in order],
                  budgets=[r["budget"] for r in records])
        self._attention(f"Function F1 of {len(records)} is ready.")
        return {}

    def describe_actions(self):
        def action(name, description, properties, required):
            return {"name": name, "description": description,
                    "input_schema": {"type": "object", "properties": properties,
                                     "required": required, "additionalProperties": False},
                    "output_schema": {"type": "object"}, "roles": ["solver"]}
        return [
            action("query", f"Call the hidden function on up to {MAX_BATCH} argument lists at once; "
                   "each call spends one query from the budget.",
                   {"calls": {"type": "array", "title": "Argument lists", "minItems": 1,
                              "maxItems": MAX_BATCH, "items": {"type": "array"},
                              "description": "Each item lists every parameter in order, e.g. [[3, 4], [0, 0]]."}},
                   ["calls"]),
            action("note", "Replace your scratchpad for the current function; the view shows it back to you.",
                   {"text": {"type": "string", "title": "Scratchpad", "maxLength": MAX_NOTE}}, ["text"]),
            action("submit", "Submit Python source defining f for the current function. "
                   "One accepted submission per function; you are told how many hidden tests passed.",
                   {"source": {"type": "string", "title": "Python source", "minLength": 1,
                               "maxLength": MAX_SOURCE}}, ["source"]),
        ]

    def _check_seat(self, seat):
        if seat != self.state["seat"]:
            raise ValueError("Unknown seat")

    def _record(self):
        st = self.state
        return st["records"][st["current"]] if st["phase"] == "playing" else None

    def observe(self, seat):
        self._check_seat(seat)
        st = self.state
        finished = st["phase"] == "finished"
        rec = self._record()
        registry = {fn["id"]: fn for fn in library.FUNCTIONS}
        completed = [{"label": r["label"], "signature": signature_text(registry[r["id"]]),
                      "passed": r["passed"], "total": r["total"]}
                     for r in st["records"] if r["passed"] is not None]
        view = {"phase": st["phase"], "function_count": len(st["records"]),
                "completed": completed,
                "score_so_far": {"passed": sum(c["passed"] for c in completed),
                                 "total": sum(c["total"] for c in completed)},
                "current": None, "legal_actions": [] if finished else ["query", "note", "submit"]}
        if rec is not None:
            fn = registry[rec["id"]]
            view["current"] = {"label": rec["label"], "number": st["current"] + 1,
                               "signature": signature(fn), "query_budget": rec["budget"],
                               "queries_left": rec["budget"] - spent(rec),
                               "queries": deepcopy(rec["queries"]), "queries_omitted": 0,
                               "note": rec["note"]}
        return view

    def agent_view(self, seat):
        view = self.observe(seat)
        view["earlier_completed_omitted"] = 0
        while len(json.dumps(view).encode("utf-8")) > VIEW_LIMIT:
            current = view["current"]
            if current and current["queries"]:
                current["queries"].pop(0)
                current["queries_omitted"] += 1
            else:
                view["completed"].pop(0)
                view["earlier_completed_omitted"] += 1
        return view

    def handle_input(self, seat, text):
        raise ValueError("Table talk is disabled. Use query, note, or submit.")

    def invoke(self, seat, action, arguments):
        self._check_seat(seat)
        rec = self._record()
        if rec is None:
            raise ValueError("The run is finished")
        if action not in ("query", "note", "submit"):
            raise ValueError("Unknown action")
        field = {"query": "calls", "note": "text", "submit": "source"}[action]
        if not isinstance(arguments, dict) or set(arguments) != {field}:
            raise ValueError(f"Expected exactly one argument: {field}")
        return getattr(self, f"_{action}")(rec, arguments[field])

    def _query(self, rec, calls):
        fn = {f["id"]: f for f in library.FUNCTIONS}[rec["id"]]
        left = rec["budget"] - spent(rec)
        specs = param_specs(fn)
        try:
            if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_BATCH:
                raise ValueError(f"Send between 1 and {MAX_BATCH} calls per query")
            if len(calls) > left:
                raise ValueError(f"Only {left} quer{'y' if left == 1 else 'ies'} left for this function")
            for number, args in enumerate(calls, 1):
                if not isinstance(args, list) or len(args) != len(specs):
                    raise ValueError(f"Call {number} must list {len(specs)} argument(s) in order: "
                                     + ", ".join(spec["name"] for spec in specs))
                for spec, value in zip(specs, args):
                    check_value(spec["type"], spec, value, f"Call {number}, {spec['name']}")
        except ValueError as error:
            # A function that was submitted is closed, so calls written for it land on the next one.
            raise ValueError(f"The current function is {rec['label']}; an earlier function cannot be queried again. {error}") from None
        results = []
        for args in calls:
            try:
                output = json.loads(json.dumps(fn["impl"](*deepcopy(args)), allow_nan=False))
                results.append({"args": args, "output": output})
            except Exception as error:  # the hidden function may legitimately raise
                results.append({"args": args, "error": type(error).__name__,
                                "message": str(error)[:ERROR_MESSAGE_LIMIT]})
        rec["queries"].extend(results)
        st = self.state
        st["revision"] += 1
        after = rec["budget"] - spent(rec)
        self._log("query", rec, outcome="accepted", calls=calls,
                  results=[{k: v for k, v in r.items() if k != "args"} for r in results],
                  queries_left=after)
        self._attention(f"{rec['label']}: {after} quer{'y' if after == 1 else 'ies'} left.")
        return {"results": results, "queries_left": after}

    def _note(self, rec, text):
        if not isinstance(text, str) or len(text) > MAX_NOTE:
            raise ValueError(f"Notes must be text of at most {MAX_NOTE} characters")
        rec["note"] = text
        self._log("note", rec, outcome="accepted", chars=len(text))
        progress(self.state["revision"], waiting_for=[self.state["seat"]])
        return {"saved": True}

    def _submit(self, rec, source):
        fn = {f["id"]: f for f in library.FUNCTIONS}[rec["id"]]
        if not isinstance(source, str) or not source.strip() or len(source) > MAX_SOURCE:
            raise ValueError(f"Source must be non-empty text of at most {MAX_SOURCE} characters")
        sandbox.check_source(source, len(fn["params"]))
        tests = fn["tests"]
        ran = sandbox.run_cases(source, [t["args"] for t in tests])
        tolerance = fn.get("tolerance")
        case_results = []
        for test, outcome in zip(tests, ran):
            passed = outcome["ok"] and sandbox.matches(test["expected"], outcome["value"], tolerance)
            case_results.append({"args": test["args"], "expected": test["expected"],
                                 "actual": outcome.get("value"), "error": outcome.get("error"),
                                 "passed": bool(passed)})
        passed = sum(case["passed"] for case in case_results)
        label = rec["label"]
        self._settle(rec, source, passed, case_results, forfeited=False)
        following = self._record()
        closed = f"{label} scored {passed}/{len(tests)} and is closed: it cannot be queried, changed, or resubmitted."
        message = (f"{closed} Move on to {following['label']} now; it has its own fresh query budget."
                   if following else f"{closed} That was the last function; the run is complete.")
        return {"function": label, "passed": passed, "total": len(tests),
                "next": following["label"] if following else None, "message": message}

    def _settle(self, rec, source, passed, case_results, *, forfeited):
        st = self.state
        rec.update(submission=source, passed=passed, case_results=case_results, forfeited=forfeited)
        st["revision"] += 1
        self._log("submit", rec, seat="environment" if forfeited else st["seat"],
                  outcome="forfeited" if forfeited else "accepted", passed=passed,
                  total=rec["total"], case_results=case_results)
        st["current"] += 1
        if st["current"] >= len(st["records"]):
            st["phase"] = "finished"
            self._log("finish", None, seat="environment", outcome="accepted",
                      passed=sum(r["passed"] for r in st["records"]),
                      total=sum(r["total"] for r in st["records"]))
            self._attention("")
        else:
            self._attention(f"{rec['label']} scored {passed}/{rec['total']}. "
                            f"Function {st['records'][st['current']]['label']} of "
                            f"{len(st['records'])} is ready.")

    def missed_turn(self, seat, report):
        """A turn ended without an action: warn twice, then forfeit the current function."""
        rec = self._record()
        if rec is None:
            return {}
        misses = report["misses"]
        if report["cause"] != "suspended" and misses <= MISS_WARNINGS and misses <= report["limit"]:
            self._log("missed_turn", rec, seat="environment", outcome="warned", cause=report["cause"])
            remaining = "another turn" if misses == MISS_WARNINGS else "two more turns"
            notify([seat], f"Warning {misses} of {MISS_WARNINGS}: your turn ended without an action on "
                   f"{rec['label']}. {self._guidance(rec)} If you miss {remaining} in a row, this "
                   "function is forfeited with a score of zero.", actionable=True)
            progress(self.state["revision"], waiting_for=[seat])
            return {"warned": True}
        self._log("missed_turn", rec, seat="environment", outcome="forfeited", cause=report["cause"])
        self._settle(rec, None, 0, [], forfeited=True)
        return {"forfeited": rec["label"]}

    def _summary(self):
        records = self.state["records"]
        passed = sum(r["passed"] for r in records)
        total = sum(r["total"] for r in records)
        registry = {fn["id"]: fn for fn in library.FUNCTIONS}
        tiers = []
        for tier in library.TIERS:
            mine = [r for r in records if registry[r["id"]]["tier"] == tier]
            if mine:
                tiers.append(f"{tier} {sum(r['passed'] for r in mine)}/{sum(r['total'] for r in mine)}")
        parts = [f"{r['label']} [{registry[r['id']]['tier']}] {registry[r['id']]['title']} "
                 f"{r['passed']}/{r['total']}" + (" (forfeited)" if r["forfeited"] else "")
                 for r in records]
        return (f"Score {passed}/{total} ({100 * passed / total:.1f}%). By tier: "
                + ", ".join(tiers) + ". " + "; ".join(parts))

    def _attention(self, message):
        st = self.state
        if st["phase"] == "finished":
            progress(st["revision"], waiting_for=[])
            finish(self._summary())
        else:
            progress(st["revision"], waiting_for=[st["seat"]])
            notify([st["seat"]], f"{message} {self._guidance(self._record())}", actionable=True)

    def _guidance(self, rec):
        if rec["budget"] - spent(rec) > 0:
            return "Probe with query, then submit when ready."
        return "No queries remain: submit your best implementation now."

    def _log(self, kind, rec, *, seat=None, **fields):
        st = self.state
        st["seq"] += 1
        st["log"].append({"seq": st["seq"], "type": kind, "function": rec["id"] if rec else None,
                          "label": rec["label"] if rec else None, "revision": st["revision"],
                          "seat": seat or st["seat"], **fields})

    def snapshot(self):
        return deepcopy(self.state)

    def restore(self, snapshot):
        self.state = deepcopy(snapshot)
        return {}

    def dispose(self):
        return {}


environment = FunctionDiscovery()
