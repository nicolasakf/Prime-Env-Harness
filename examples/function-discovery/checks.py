"""Behavioral checks. Run with the draft's selected execution backend."""
import inspect
import json
import random
import re
from pathlib import Path

import functions as library
import sdk
from environment import (FunctionDiscovery, KINDS, MAX_BATCH, NULLABLE, VIEW_LIMIT, check_value,
                         param_specs, signature, signature_text)
import sandbox

SEAT = "solo"
LEAKS = ('"tests"', '"expected"', '"impl"', '"title"', '"case_results"', '"submission"')


def committed(game, method, *args):
    """Run one host request and check the attention metadata it commits."""
    sdk._begin_request(method)
    result = getattr(game, method)(*args)
    meta = sdk._response_metadata()
    finished = game.state["phase"] == "finished"
    assert meta["progress"] == {"revision": game.state["revision"],
                                "waiting_for": [] if finished else [SEAT]}
    assert ("finished" in meta) == finished
    notices = meta.get("notices", [])
    for notice in notices:
        assert notice["to"] == [SEAT] and notice["wake"] and notice["actionable"]
    is_note = method == "invoke" and args[1] == "note"
    assert len(notices) == (0 if is_note or finished else 1), notices
    leakless(game)
    return result


def leakless(game):
    funcs = library.FUNCTIONS
    assert len(json.dumps(game.agent_view(SEAT)).encode()) <= VIEW_LIMIT + 2048
    for view in (game.observe(SEAT), game.agent_view(SEAT)):
        text = json.dumps(view)
        assert not [key for key in LEAKS if key in text], text
        if game.state["phase"] == "playing":
            assert not [fn["id"] for fn in funcs if f'"{fn["id"]}"' in text]
            assert not [fn["title"] for fn in funcs if fn["title"] in text]


def act(game, action, arguments):
    return committed(game, "invoke", SEAT, action, arguments)


def rejected(game, action, arguments, seat=SEAT):
    before = json.loads(json.dumps(game.snapshot()))
    sdk._begin_request("invoke")
    try:
        game.invoke(seat, action, arguments)
    except ValueError:
        pass
    else:
        raise AssertionError(f"Accepted illegal action: {action} {arguments}")
    assert game.snapshot() == before
    assert sdk._response_metadata() == {}


def new_game(functions=(), budget=20, tiers=(), seats=({"id": SEAT, "role": "solver"},)):
    game = FunctionDiscovery()
    committed(game, "initialize", {"seats": list(seats), "config": {
        "query_budget": budget, "functions": list(functions), "tiers": list(tiers)}})
    return game


def reference_source(fn):
    return re.sub(r"def \w+\(", "def f(", inspect.getsource(fn["impl"]), count=1)


def check_module():
    ids = [fn["id"] for fn in library.FUNCTIONS]
    assert ids and len(set(ids)) == len(ids)
    with Path(__file__).with_name("environment.json").open() as manifest:
        tier_enum = json.load(manifest)["setup_schema"]["properties"]["tiers"]["items"]["enum"]
    assert tier_enum == list(library.TIERS)
    assert {fn["tier"] for fn in library.FUNCTIONS} == set(library.TIERS)
    for fn in library.FUNCTIONS:
        assert fn["title"] and fn["returns"] and fn["tests"]
        assert isinstance(fn["description"], str) and fn.get("raises", False) in (True, False)
        assert fn["returns"].removesuffix(NULLABLE) in KINDS, fn["returns"]
        names = [p["name"] for p in fn["params"]]
        assert fn["params"] and len(set(names)) == len(names)
        assert all(p["type"] in KINDS and name.isidentifier() for p, name in zip(fn["params"], names))
        for test in fn["tests"]:
            for spec, value in zip(param_specs(fn), test["args"]):
                check_value(spec["type"], spec, value, "test")
            assert len(test["args"]) == len(fn["params"])
            assert json.loads(json.dumps(test["expected"])) == test["expected"]
            assert conforms(fn["returns"], test["expected"]), (fn["id"], test)
            assert sandbox.matches(test["expected"], fn["impl"](*json.loads(json.dumps(test["args"]))),
                                   fn.get("tolerance"))
        sandbox.check_source(reference_source(fn), len(fn["params"]))
        assert raises_somewhere(fn) == bool(fn.get("raises")), (fn["id"], "raises flag is wrong")


def conforms(kind, value):
    """Whether a JSON value has the declared return type."""
    if kind.endswith(NULLABLE):
        return value is None or conforms(kind.removesuffix(NULLABLE), value)
    if kind.startswith("list["):
        return isinstance(value, list) and all(conforms(kind[5:-1], item) for item in value)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "float":
        return isinstance(value, float)
    return isinstance(value, str)


def random_value(rng, kind, spec, *, item=False):
    if kind.startswith("list["):
        return [random_value(rng, kind[5:-1], spec, item=True)
                for _ in range(rng.randint(0, min(spec["max_len"], 6)))]
    if kind == "int":
        low, high = max(spec["min"], -50), min(spec["max"], 50)
        if low <= high and rng.random() < 0.5:
            return rng.randint(low, high)
        return rng.randint(spec["min"], spec["max"])
    if kind == "float":
        return rng.uniform(spec["min"], spec["max"])
    if kind == "bool":
        return rng.random() < 0.5
    limit = spec["max_item_len"] if item else spec["max_len"]
    alphabet = rng.choice(["abc", "01", "0123456789", "ab c()[]{}+-*12", "abcXYZ 019,.!"])
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, min(limit, 8))))


def raises_somewhere(fn):
    """Fuzz the reference implementation with in-bounds inputs to see whether it can raise."""
    rng = random.Random(1)
    specs = param_specs(fn)
    for _ in range(1500):
        args = [random_value(rng, spec["type"], spec) for spec in specs]
        try:
            fn["impl"](*json.loads(json.dumps(args)))
        except Exception:
            return True
    return False


def check_setup():
    game = new_game()
    first = game.observe(SEAT)
    assert first["current"]["label"] == "F1" and first["function_count"] == len(library.FUNCTIONS)
    assert first["current"]["queries_left"] == 20 and first["current"]["queries"] == []
    assert first["legal_actions"] == ["query", "note", "submit"]
    ids = [fn["id"] for fn in library.FUNCTIONS]
    subset = new_game([ids[2], ids[0]], budget=4)
    assert [r["id"] for r in subset.state["records"]] == [ids[2], ids[0]]
    assert subset.observe(SEAT)["current"]["queries_left"] == 4
    by_tier = {tier: [fn["id"] for fn in library.FUNCTIONS if fn["tier"] == tier] for tier in library.TIERS}
    hard = new_game(tiers=["extreme", "hard"])
    assert [r["id"] for r in hard.state["records"]] == by_tier["hard"] + by_tier["extreme"]
    mixed = new_game([by_tier["hard"][1], ids[0], by_tier["hard"][0]], tiers=["hard"])
    assert [r["id"] for r in mixed.state["records"]] == [by_tier["hard"][1], by_tier["hard"][0]]
    for functions, tiers in ((["nope"], []), ([ids[0], ids[0]], []), ([], ["impossible"]),
                             ([by_tier["starter"][0]], ["extreme"])):
        try:
            FunctionDiscovery().initialize({"seats": [{"id": SEAT, "role": "solver"}], "config": {
                "query_budget": 5, "functions": functions, "tiers": tiers}})
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted selection {functions} {tiers}")
    try:
        FunctionDiscovery().initialize({"seats": [{"id": "a", "role": "solver"}, {"id": "b", "role": "solver"}],
                                        "config": {}})
    except ValueError:
        pass
    else:
        raise AssertionError("Accepted two seats")
    rejected(game, "query", {"calls": [[1]]}, seat="stranger")
    try:
        game.handle_input(SEAT, "hello")
    except ValueError:
        pass
    else:
        raise AssertionError("Table talk accepted")
    assert [a["name"] for a in game.describe_actions()] == ["query", "note", "submit"]


def check_signatures():
    """Every function shows a complete, plain signature before any query is made."""
    for fn in library.FUNCTIONS:
        game = new_game([fn["id"]])
        shown = game.agent_view(SEAT)["current"]["signature"]
        params = ", ".join(f"{p['name']}: {p['type']}" for p in fn["params"])
        assert shown["text"] == f"f({params}) -> {fn['returns']}" == signature_text(fn)
        assert shown["function"] == "f" and shown["returns"] == fn["returns"]
        assert [(p["name"], p["type"]) for p in shown["params"]] == [(p["name"], p["type"]) for p in fn["params"]]
        assert all(p["constraints"] for p in shown["params"])
        assert ("raises" in shown) == bool(fn.get("raises"))
        assert shown == signature(fn)
    assert signature(library.FUNCTIONS[15])["params"][0]["constraints"] == "int, 1900 to 2100"
    assert signature(library.FUNCTIONS[6])["params"][0]["constraints"] == "list of at most 20 ints, each -100 to 100"
    assert signature(library.FUNCTIONS[18])["params"][0]["constraints"] == (
        "list of at most 15 strings, each at most 6 characters")


def check_queries():
    game = new_game(["f04"], budget=5)
    fn = {f["id"]: f for f in library.FUNCTIONS}["f04"]
    result = act(game, "query", {"calls": [[12, 18], [0, 0], [17, 13]]})
    assert result == {"results": [{"args": [12, 18], "output": 6}, {"args": [0, 0], "output": 0},
                                  {"args": [17, 13], "output": 1}], "queries_left": 2}
    view = game.observe(SEAT)["current"]
    assert view["queries_left"] == 2 and view["queries"] == result["results"]
    assert view["signature"]["params"][0] == {
        "name": "a", "type": "int", "min": 0, "max": 10**6, "constraints": "int, 0 to 1000000"}
    assert game.state["revision"] == 1
    for calls in ([[1, 2], [3, 4], [5, 6]], [], [[1]], [[1, 2, 3]], [["1", 2]], [[True, 2]],
                  [[1.5, 2]], [[-1, 2]], [[1, 10**6 + 1]], "x", [1, 2], [[1, 2]] * (MAX_BATCH + 1)):
        rejected(game, "query", {"calls": calls})
    rejected(game, "query", {"calls": [[1, 2]], "extra": 1})
    rejected(game, "dance", {})
    act(game, "query", {"calls": [[4, 6], [9, 6]]})
    assert game.observe(SEAT)["current"]["queries_left"] == 0
    rejected(game, "query", {"calls": [[1, 1]]})
    assert fn["impl"](4, 6) == 2


def check_hidden_failures():
    """Reference errors and unserializable outputs become free, visible error entries."""
    saved = library.FUNCTIONS
    try:
        def broken(x):
            if x == 0:
                raise ValueError("bad input")
            return {x} if x == 1 else x

        library.FUNCTIONS = [{"id": "g1", "tier": "easy", "title": "Broken", "params": [{"name": "x", "type": "int"}],
                              "returns": "int", "impl": broken, "tests": [{"args": [2], "expected": 2}]}]
        game = new_game(budget=3)
        result = act(game, "query", {"calls": [[0], [1], [5]]})
        assert result["results"][0] == {"args": [0], "error": "ValueError", "message": "bad input"}
        assert result["results"][1]["args"] == [1] and result["results"][1]["error"] == "TypeError"
        assert isinstance(result["results"][1]["message"], str)
        assert result["results"][2] == {"args": [5], "output": 5}
        # Only the call that returned an output is charged, so the agent can try again.
        assert result["queries_left"] == 2
        assert game.observe(SEAT)["current"]["queries"] == result["results"]
        assert act(game, "query", {"calls": [[0], [0]]})["queries_left"] == 2
        assert act(game, "query", {"calls": [[7], [8]]})["queries_left"] == 0
        rejected(game, "query", {"calls": [[0]]})
        assert game._guidance(game._record()).startswith("No queries remain")
    finally:
        library.FUNCTIONS = saved


def check_notes():
    game = new_game(["f01"])
    revision = game.state["revision"]
    assert act(game, "note", {"text": "looks linear"}) == {"saved": True}
    assert game.observe(SEAT)["current"]["note"] == "looks linear"
    assert game.state["revision"] == revision
    act(game, "note", {"text": "slope 3"})
    assert game.observe(SEAT)["current"]["note"] == "slope 3"
    rejected(game, "note", {"text": "x" * 4001})
    rejected(game, "note", {"text": 5})


def check_submissions():
    game = new_game(["f01", "f09"])
    for source in ("def f(x:\n", "def g(x): return 1", "def f(x, y): return 1", "def f(*a): return 1",
                   "import os\ndef f(x): return 1", "def f(x): return ().__class__",
                   "def f(x): return open('a')", "def f(x): return '{0.__class__}'.format(x)",
                   "class A:\n    pass\ndef f(x): return 1", "from subprocess import run\ndef f(x): return 1",
                   "", "   "):
        rejected(game, "submit", {"source": source})
    # One timeout on x == 999 fails only that case.
    result = act(game, "submit", {"source": "def f(x):\n    while x == 999:\n        pass\n    return 3 * x - 7\n"})
    assert result == {"function": "F1", "passed": 11, "total": 12, "next": "F2",
                      "message": "F1 scored 11/12 and is closed: it cannot be queried, changed, or resubmitted. "
                                 "Move on to F2 now; it has its own fresh query budget."}
    record = game.state["records"][0]
    assert [c["error"] for c in record["case_results"] if c["error"]] == ["Timeout"]
    assert game.observe(SEAT)["completed"] == [{"label": "F1", "signature": "f(x: int) -> int",
                                               "passed": 11, "total": 12}]
    assert game.observe(SEAT)["current"]["label"] == "F2"
    # Float tolerance accepts tiny drift and the view tells the agent about it.
    assert game.observe(SEAT)["current"]["signature"]["tolerance"] == 1e-9
    result = act(game, "submit", {"source": "def f(x):\n    return min(max(2.5 * x, -10.0), 10.0) + 1e-12\n"})
    assert result == {"function": "F2", "passed": 12, "total": 12, "next": None,
                      "message": "F2 scored 12/12 and is closed: it cannot be queried, changed, or resubmitted. "
                                 "That was the last function; the run is complete."}
    assert game.state["phase"] == "finished"
    view = game.observe(SEAT)
    assert view["current"] is None and view["legal_actions"] == []
    assert view["score_so_far"] == {"passed": 23, "total": 24}
    for action, arguments in (("query", {"calls": [[1]]}), ("note", {"text": "x"}),
                              ("submit", {"source": "def f(x): return 1"})):
        rejected(game, action, arguments)


def check_closed_function_is_unreachable():
    """After a submit, calls written for the closed function go to the next one and say so."""
    game = new_game(["f04", "f01"])
    act(game, "query", {"calls": [[12, 18]]})
    act(game, "submit", {"source": "import math\ndef f(a, b):\n    return math.gcd(a, b)\n"})
    assert game.observe(SEAT)["current"]["label"] == "F2" and game.observe(SEAT)["current"]["queries"] == []
    before = json.loads(json.dumps(game.snapshot()))
    sdk._begin_request("invoke")
    try:
        game.invoke(SEAT, "query", {"calls": [[12, 18]]})
    except ValueError as error:
        assert str(error) == ("The current function is F2; an earlier function cannot be queried again. "
                              "Call 1 must list 1 argument(s) in order: x")
    else:
        raise AssertionError("A call shaped for the closed function was accepted")
    assert game.snapshot() == before and sdk._response_metadata() == {}
    rejected(game, "query", {"calls": [[10**6]]})


def check_error_submissions():
    game = new_game(["f01", "f02", "f03"])
    result = act(game, "submit", {"source": "def f(x):\n    return 1 // 0\n"})
    assert result["passed"] == 0
    assert {c["error"] for c in game.state["records"][0]["case_results"]} == {"ZeroDivisionError"}
    result = act(game, "submit", {"source": "def f(x):\n    return (x, x)\n"})
    assert result["passed"] == 0
    result = act(game, "submit", {"source": "import re\nVALUE = 1 // 0\ndef f(n): return 1\n"})
    assert result["passed"] == 0 and game.state["phase"] == "finished"


def check_full_run():
    game = new_game()
    total = 0
    for fn in library.FUNCTIONS:
        assert game.observe(SEAT)["current"]["label"] == f"F{library.FUNCTIONS.index(fn) + 1}"
        act(game, "query", {"calls": [list(fn["tests"][0]["args"])]})
        result = act(game, "submit", {"source": reference_source(fn)})
        assert result["passed"] == result["total"] == len(fn["tests"]), (fn["id"], result)
        total += result["total"]
    assert game.state["phase"] == "finished"
    sdk._begin_request("invoke")
    assert [r["passed"] for r in game.state["records"]] == [len(fn["tests"]) for fn in library.FUNCTIONS]
    summary = game._summary()
    tiers = ", ".join(f"{tier} {n}/{n}" for tier in library.TIERS
                      for n in [sum(len(fn["tests"]) for fn in library.FUNCTIONS if fn["tier"] == tier)])
    assert summary.startswith(f"Score {total}/{total} (100.0%). By tier: {tiers}. ")
    assert all(fn["title"] in summary for fn in library.FUNCTIONS)
    log = game.state["log"]
    assert [entry["seq"] for entry in log] == list(range(1, len(log) + 1))
    assert [entry["type"] for entry in log].count("submit") == len(library.FUNCTIONS)
    assert log[-1]["type"] == "finish" and log[-1]["passed"] == total


def check_view_bound():
    game = new_game(["f07"], budget=200)
    for _ in range(10):
        act(game, "query", {"calls": [[list(range(i, i + 20))] for i in range(-100, -80)]})
    full = json.dumps(game.agent_view(SEAT))
    assert len(full.encode()) <= VIEW_LIMIT
    current = game.agent_view(SEAT)["current"]
    assert current["queries_omitted"] > 0
    assert current["queries"] == game.observe(SEAT)["current"]["queries"][current["queries_omitted"]:]
    assert game.observe(SEAT)["current"]["queries_left"] == 0


def check_missed_turns():
    game = new_game(["f01", "f02"])
    before = json.loads(json.dumps(game.snapshot()))
    assert committed(game, "missed_turn", SEAT, {"cause": "idle", "misses": 1, "limit": 2}) == {"warned": True}
    first = sdk._response_metadata()["notices"][0]["message"]
    assert first.startswith("Warning 1 of 2:") and "two more turns" in first and "Probe with query" in first
    assert game.state["records"] == before["records"] and game.state["current"] == 0
    assert committed(game, "missed_turn", SEAT, {"cause": "deadline", "misses": 2, "limit": 2}) == {"warned": True}
    second = sdk._response_metadata()["notices"][0]["message"]
    assert second.startswith("Warning 2 of 2:") and "another turn" in second
    assert game.state["records"] == before["records"] and game.state["current"] == 0
    assert committed(game, "missed_turn", SEAT, {"cause": "idle", "misses": 3, "limit": 2}) == {"forfeited": "F1"}
    record = game.state["records"][0]
    assert (record["passed"], record["forfeited"], record["submission"]) == (0, True, None)
    assert game.observe(SEAT)["current"]["label"] == "F2"
    committed(game, "missed_turn", SEAT, {"cause": "suspended", "misses": 1, "limit": 2})
    assert game.state["phase"] == "finished"
    assert game._summary() == ("Score 0/24 (0.0%). By tier: starter 0/24. F1 [starter] Affine map "
                               "0/12 (forfeited); F2 [starter] Quadratic mod 17 0/12 (forfeited)")
    sdk._begin_request("missed_turn")
    assert game.missed_turn(SEAT, {"cause": "idle", "misses": 3, "limit": 2}) == {}
    assert sdk._response_metadata() == {}
    # A host that grants fewer re-prompts forfeits sooner; a warning is never issued past the limit.
    strict = new_game(["f01", "f02"])
    assert committed(strict, "missed_turn", SEAT, {"cause": "idle", "misses": 1, "limit": 0}) == {"forfeited": "F1"}


def check_wake_text():
    """The notice names what to do next, and never offers probing once the budget is spent."""
    game = new_game(["f01", "f02"], budget=2)
    act(game, "query", {"calls": [[1]]})
    notice = sdk._response_metadata()["notices"][0]["message"]
    assert notice == "F1: 1 query left. Probe with query, then submit when ready."
    act(game, "query", {"calls": [[2]]})
    notice = sdk._response_metadata()["notices"][0]["message"]
    assert notice == "F1: 0 queries left. No queries remain: submit your best implementation now."
    committed(game, "missed_turn", SEAT, {"cause": "idle", "misses": 1, "limit": 2})
    warning = sdk._response_metadata()["notices"][0]["message"]
    assert "No queries remain" in warning and "Probe" not in warning
    act(game, "submit", {"source": "def f(x): return 3 * x - 7"})
    notice = sdk._response_metadata()["notices"][0]["message"]
    assert notice == ("F1 scored 12/12. Function F2 of 2 is ready. "
                      "Probe with query, then submit when ready.")


def game_at(snapshot):
    game = FunctionDiscovery()
    game.restore(json.loads(json.dumps(snapshot)))
    return game


def check_restore():
    game = new_game(["f01", "f02"], budget=6)
    checkpoints = []

    def save():
        checkpoints.append((json.loads(json.dumps(game.snapshot())), game.observe(SEAT)))

    save()
    act(game, "query", {"calls": [[1], [2]]})
    act(game, "note", {"text": "hypothesis"})
    save()
    act(game, "submit", {"source": "def f(x): return 3 * x - 7"})
    save()
    act(game, "submit", {"source": "def f(x): return 0"})
    save()
    for snapshot, view in checkpoints:
        fresh = game_at(snapshot)
        assert fresh.snapshot() == snapshot
        assert fresh.observe(SEAT) == view
    sdk._begin_request("restore")
    game_at(checkpoints[0][0])
    assert sdk._response_metadata() == {}
    resumed = game_at(checkpoints[1][0])
    act(resumed, "submit", {"source": "def f(x): return 3 * x - 7"})
    assert resumed.snapshot() == checkpoints[2][0]


check_module()
check_setup()
check_signatures()
check_queries()
check_hidden_failures()
check_notes()
check_submissions()
check_closed_function_is_unreachable()
check_error_submissions()
check_full_run()
check_view_bound()
check_missed_turns()
check_wake_text()
check_restore()
print("Function discovery behavioral checks passed")
