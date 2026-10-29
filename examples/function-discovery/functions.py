"""The functions the agent must reverse-engineer. Edit FUNCTIONS to change the game.

Each entry is a dict:

  id           Unique slug. It appears in the agent's system prompt whenever the
               `functions` setup option is used, so keep it neutral (f01, f02, ...).
  title        Human-readable name; revealed only in the final summary.
  tier         One of TIERS. Never shown to the agent; the `tiers` setup option
               selects by it, and the final summary totals each tier.
  params       Ordered list of {"name", "type", ...}. Types: int, float, str, bool,
               list[int], list[float], list[str]. Optional bounds: "min"/"max" for
               numbers (elements, for lists; default +-10**12), "max_len" for strings
               and lists (default 200 / 50), "max_item_len" for list[str] elements
               (default 50). The agent sees every bound, and queries outside them
               are rejected.
  returns      Return type shown in the signature: one of int, float, str, bool,
               list[int], list[float], list[str], optionally followed by " | null"
               (e.g. "int | null") when the function can return None. Every
               hidden test's `expected` must match it (the checks verify this).
  raises       Optional bool. True when some in-bounds inputs make `impl` raise;
               the signature then says so. Raised errors are free for the agent
               and shown with their type and message, so keep messages neutral
               (e.g. "invalid input") when they would reveal the algorithm.
  description  Optional extra hint shown to the agent (may be empty). Use it to name the
               input domain when the signature alone leaves the interesting inputs
               unguessable (a bare `str`), without revealing what the function does.
  impl         The reference implementation. It answers the agent's queries and must
               return JSON-compatible values (None, bool, int, float, str, list).
               Keep it self-contained (imports and helpers inside the def): the
               checks submit its source as a perfect answer. It may raise on
               inputs it rejects; the agent then sees only the exception name.
  tests        Hidden cases: {"args": [...], "expected": value}. The score is the
               number of these a submission gets right; include edge cases.
  query_budget Optional per-function override of the setup option (default None).
  tolerance    Optional relative/absolute tolerance for numeric answers (default None).
"""


TIERS = ("starter", "easy", "medium", "hard", "extreme")


def cases(impl, *arg_lists):
    """Build hidden tests whose expected values come from the reference implementation."""
    return [{"args": list(args), "expected": impl(*args)} for args in arg_lists]


def affine(x):
    return 3 * x - 7


def quadratic_mod(x):
    return (x * x + 3 * x + 1) % 17


def digit_sum(n):
    return sum(int(digit) for digit in str(n))


def gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def collatz_step(n):
    return n // 2 if n % 2 == 0 else 3 * n + 1


def caesar3(s):
    shifted = []
    for ch in s:
        if "a" <= ch <= "z":
            shifted.append(chr((ord(ch) - 97 + 3) % 26 + 97))
        elif "A" <= ch <= "Z":
            shifted.append(chr((ord(ch) - 65 + 3) % 26 + 65))
        else:
            shifted.append(ch)
    return "".join(shifted)


def unique_descending(xs):
    return sorted(set(xs), reverse=True)


def gray_code(n):
    return n ^ (n >> 1)


def clamp_scaled(x):
    return min(max(2.5 * x, -10.0), 10.0)


# --- easy -------------------------------------------------------------------

def count_vowels(s):
    return sum(ch in "aeiouAEIOU" for ch in s)


def is_palindrome(s):
    return s == s[::-1]


def spread(xs):
    return max(xs) - min(xs) if xs else 0


def fizzbuzz(n):
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)


# --- medium -----------------------------------------------------------------

def run_length(s):
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(f"{s[i]}{j - i}")
        i = j
    return "".join(out)


def second_largest(xs):
    distinct = sorted(set(xs), reverse=True)
    return distinct[1] if len(distinct) > 1 else None


def weekday(year, month, day):
    import datetime
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names[datetime.date(year, month, day).weekday()]


def bracket_depth(s):
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    deepest = 0
    for ch in s:
        if ch in "([{":
            stack.append(ch)
            deepest = max(deepest, len(stack))
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return -1
    return deepest if not stack else -1


# --- hard -------------------------------------------------------------------

def luhn_valid(s):
    if not s or not s.isdigit():
        raise ValueError("invalid input")
    total = 0
    for i, ch in enumerate(reversed(s)):
        digit = int(ch)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def rpn(tokens):
    stack = []
    try:
        for token in tokens:
            if token in ("+", "-", "*"):
                b = stack.pop()
                a = stack.pop()
                stack.append(a + b if token == "+" else a - b if token == "-" else a * b)
            else:
                stack.append(int(token))
    except (IndexError, ValueError):
        raise ValueError("invalid input") from None
    if len(stack) != 1:
        raise ValueError("invalid input")
    return stack[0]


def knight_distance(x, y):
    from collections import deque
    limit = max(abs(x), abs(y)) + 4
    seen = {(0, 0): 0}
    queue = deque([(0, 0)])
    while queue:
        cx, cy = queue.popleft()
        if (cx, cy) == (x, y):
            return seen[(cx, cy)]
        for dx, dy in ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)):
            nxt = (cx + dx, cy + dy)
            if nxt not in seen and abs(nxt[0]) <= limit and abs(nxt[1]) <= limit:
                seen[nxt] = seen[(cx, cy)] + 1
                queue.append(nxt)
    raise ValueError("unreachable")


def digit_sum_sort(xs):
    return sorted(xs, key=lambda v: (sum(int(ch) for ch in str(v)), -v))


# --- extreme ----------------------------------------------------------------

def cellular(cells, steps):
    if any(ch not in "01" for ch in cells):
        raise ValueError("invalid input")
    rule = 110
    row = [int(ch) for ch in cells]
    size = len(row)
    for _ in range(steps):
        row = [(rule >> (4 * row[i - 1] + 2 * row[i] + row[(i + 1) % size])) & 1
               for i in range(size)]
    return "".join(str(cell) for cell in row)


def hidden_machine(s):
    table = {0: {"a": 1, "b": 0, "c": 2}, 1: {"a": 2, "b": 3, "c": 0},
             2: {"a": 2, "b": 1, "c": 3}, 3: {"a": 0, "b": 3, "c": 1}}
    state = 0
    for ch in s:
        if ch not in "abc":
            raise ValueError("invalid input")
        state = table[state][ch]
    return state


def regions(a, b):
    if a > b:
        return (a * b) % 97
    if a == b:
        return a ^ 11
    return (b - a) ** 2 // 3


def word_rules(s):
    words = []
    for word in s.split():
        if len(word) % 2 == 1:
            words.append(word[::-1])
        else:
            words.append(word[0].upper() + word[1:-1] + word[-1].upper())
    return "-".join(sorted(words, key=len))


FUNCTIONS = [
    {
        "id": "f01", "tier": "starter", "title": "Affine map",
        "params": [{"name": "x", "type": "int", "min": -1000, "max": 1000}],
        "returns": "int", "description": "", "impl": affine,
        "tests": cases(affine, [0], [1], [-1], [2], [10], [-10], [100], [-100],
                       [999], [-1000], [1000], [37]),
    },
    {
        "id": "f02", "tier": "starter", "title": "Quadratic mod 17",
        "params": [{"name": "x", "type": "int", "min": 0, "max": 10000}],
        "returns": "int", "description": "", "impl": quadratic_mod,
        "tests": cases(quadratic_mod, [0], [1], [2], [5], [16], [17], [18], [34],
                       [100], [1234], [9999], [10000]),
    },
    {
        "id": "f03", "tier": "starter", "title": "Digit sum",
        "params": [{"name": "n", "type": "int", "min": 0, "max": 10**9}],
        "returns": "int", "description": "", "impl": digit_sum,
        "tests": cases(digit_sum, [0], [7], [10], [99], [100], [123], [999999],
                       [1000000], [123456789], [10**9], [505050]),
    },
    {
        "id": "f04", "tier": "starter", "title": "Greatest common divisor",
        "params": [{"name": "a", "type": "int", "min": 0, "max": 10**6},
                   {"name": "b", "type": "int", "min": 0, "max": 10**6}],
        "returns": "int", "description": "", "impl": gcd,
        "tests": cases(gcd, [0, 0], [0, 5], [5, 0], [12, 18], [17, 13], [48, 180],
                       [100, 100], [1, 999999], [1000000, 999999], [270, 192],
                       [81, 27], [35, 64]),
    },
    {
        "id": "f05", "tier": "starter", "title": "Collatz step",
        "params": [{"name": "n", "type": "int", "min": 1, "max": 10**6}],
        "returns": "int", "description": "", "impl": collatz_step,
        "tests": cases(collatz_step, [1], [2], [3], [4], [5], [6], [27], [100],
                       [101], [999999], [1000000]),
    },
    {
        "id": "f06", "tier": "starter", "title": "Caesar shift by 3",
        "params": [{"name": "s", "type": "str", "max_len": 40}],
        "returns": "str", "description": "", "impl": caesar3,
        "tests": cases(caesar3, [""], ["a"], ["abc"], ["xyz"], ["Hello, World!"],
                       ["ABC xyz"], ["123"], ["The quick brown fox"], ["zZ aA"],
                       ["  spaces  "], ["MiXeD-CaSe_42"]),
    },
    {
        "id": "f07", "tier": "starter", "title": "Unique values, descending",
        "params": [{"name": "xs", "type": "list[int]", "min": -100, "max": 100, "max_len": 20}],
        "returns": "list[int]", "description": "", "impl": unique_descending,
        "tests": cases(unique_descending, [[]], [[1]], [[3, 1, 2]], [[5, 5, 5]],
                       [[-1, 0, -1, 2, 2]], [[9, 8, 7]], [[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]],
                       [[-100, 100, 0, 100, -100]], [[4, 4, 3, 3, 2, 2, 1, 1]],
                       [[7, -3, 7, 12, -3, 0, 12, 5]]),
    },
    {
        "id": "f08", "tier": "starter", "title": "Gray code",
        "params": [{"name": "n", "type": "int", "min": 0, "max": 2**20}],
        "returns": "int", "description": "", "impl": gray_code,
        "tests": cases(gray_code, [0], [1], [2], [3], [4], [7], [8], [255], [256],
                       [1000], [65535], [2**20]),
    },
    {
        "id": "f09", "tier": "starter", "title": "Scaled and clamped",
        "params": [{"name": "x", "type": "float", "min": -100.0, "max": 100.0}],
        "returns": "float", "description": "", "impl": clamp_scaled,
        "tests": cases(clamp_scaled, [0.0], [1.0], [-1.0], [3.9], [4.0], [4.1], [-3.9],
                       [-4.0], [-4.1], [100.0], [-100.0], [0.5]),
        "tolerance": 1e-9,
    },
    # --- easy ---
    {
        "id": "f10", "tier": "easy", "title": "Count vowels",
        "params": [{"name": "s", "type": "str", "max_len": 40}],
        "returns": "int", "description": "", "impl": count_vowels,
        "tests": cases(count_vowels, [""], ["xyz"], ["aeiou"], ["AEIOU"], ["Hello World"],
                       ["rhythm"], ["Queueing"], ["yay"], ["1a2E3i"], ["bcdfg hjklm"]),
    },
    {
        "id": "f11", "tier": "easy", "title": "Exact palindrome",
        "params": [{"name": "s", "type": "str", "max_len": 40}],
        "returns": "bool", "description": "", "impl": is_palindrome,
        "tests": cases(is_palindrome, [""], ["a"], ["aa"], ["ab"], ["racecar"], ["Racecar"],
                       ["abba"], ["abca"], ["never odd or even"], ["12321"], ["a b a"], ["Aa"]),
    },
    {
        "id": "f12", "tier": "easy", "title": "Max minus min",
        "params": [{"name": "xs", "type": "list[int]", "min": -1000, "max": 1000, "max_len": 20}],
        "returns": "int", "description": "", "impl": spread,
        "tests": cases(spread, [[]], [[5]], [[1, 2]], [[2, 1]], [[-5, 5]], [[7, 7, 7]],
                       [[-1000, 1000]], [[3, -8, 12, 0, 4]], [[-3, -9, -1]], [[100, 50, 75]]),
    },
    {
        "id": "f13", "tier": "easy", "title": "FizzBuzz",
        "params": [{"name": "n", "type": "int", "min": 1, "max": 1000}],
        "returns": "str", "description": "", "impl": fizzbuzz,
        "tests": cases(fizzbuzz, [1], [3], [5], [15], [7], [30], [99], [100], [998], [1000], [45], [11]),
    },
    # --- medium ---
    {
        "id": "f14", "tier": "medium", "title": "Run-length encoding",
        "params": [{"name": "s", "type": "str", "max_len": 30}],
        "returns": "str", "description": "", "impl": run_length,
        "tests": cases(run_length, [""], ["a"], ["aaa"], ["aaabcc"], ["abc"], ["aabbaa"],
                       ["zzzzzzzzzzzz"], ["Aaa"], ["  x"], ["112223"], ["ababab"]),
    },
    {
        "id": "f15", "tier": "medium", "title": "Second largest distinct value",
        "params": [{"name": "xs", "type": "list[int]", "min": -100, "max": 100, "max_len": 20}],
        "returns": "int | null", "description": "", "impl": second_largest,
        "tests": cases(second_largest, [[]], [[4]], [[4, 4, 4]], [[1, 2]], [[2, 1]], [[5, 5, 3]],
                       [[9, 9, 8, 8]], [[-1, -2, -3]], [[100, -100]], [[3, 7, 7, 1, 7]],
                       [[0, 0, -1]]),
    },
    {
        "id": "f16", "tier": "medium", "title": "Day of the week",
        "params": [{"name": "year", "type": "int", "min": 1900, "max": 2100},
                   {"name": "month", "type": "int", "min": 1, "max": 12},
                   {"name": "day", "type": "int", "min": 1, "max": 31}],
        "returns": "str", "description": "", "raises": True, "impl": weekday,
        "tests": cases(weekday, [2000, 1, 1], [1900, 1, 1], [2100, 12, 31], [2024, 2, 29],
                       [1969, 7, 20], [2023, 3, 1], [1999, 12, 31], [2026, 10, 20],
                       [1912, 4, 15], [2050, 6, 15]),
    },
    {
        "id": "f17", "tier": "medium", "title": "Bracket nesting depth",
        "params": [{"name": "s", "type": "str", "max_len": 40}],
        "returns": "int", "description": "The text may contain letters, digits, spaces, and punctuation.", "impl": bracket_depth,
        "tests": cases(bracket_depth, [""], ["abc"], ["()"], ["(())"], ["([]{})"], ["([)]"],
                       [")("], ["((("], ["a(b[c{d}e]f)g"], ["{}{}{}"], ["(]"], ["[[[]]]()"]),
    },
    # --- hard ---
    {
        "id": "f18", "tier": "hard", "title": "Luhn checksum",
        "params": [{"name": "s", "type": "str", "max_len": 19}],
        "returns": "bool", "description": "The input is meant to be a string of digits; other strings may be rejected.",
        "raises": True, "impl": luhn_valid,
        "tests": cases(luhn_valid, ["0"], ["18"], ["79927398713"], ["79927398710"],
                       ["4539578763621486"], ["4539578763621487"], ["1234567812345670"],
                       ["1234567812345678"], ["59"], ["00000000000"], ["9"], ["26"]),
    },
    {
        "id": "f19", "tier": "hard", "title": "Postfix arithmetic",
        "params": [{"name": "tokens", "type": "list[str]", "max_len": 15, "max_item_len": 6}],
        "returns": "int", "description": "Each item is a short string token: a number or a symbol.",
        "raises": True, "impl": rpn,
        "tests": cases(rpn, [["7"]], [["2", "3", "+"]], [["2", "3", "-"]], [["4", "5", "*"]],
                       [["1", "2", "+", "3", "*"]], [["5", "1", "2", "+", "4", "*", "+", "3", "-"]],
                       [["-4", "3", "*"]], [["10", "2", "-", "3", "-"]], [["0", "9", "*"]],
                       [["6", "2", "3", "*", "-"]]),
    },
    {
        "id": "f20", "tier": "hard", "title": "Knight move distance",
        "params": [{"name": "x", "type": "int", "min": -15, "max": 15},
                   {"name": "y", "type": "int", "min": -15, "max": 15}],
        "returns": "int", "description": "", "impl": knight_distance,
        "tests": cases(knight_distance, [0, 0], [1, 2], [1, 0], [1, 1], [2, 2], [0, 3],
                       [-3, 0], [4, 4], [15, 15], [-15, 7], [7, -1], [10, 0]),
    },
    {
        "id": "f21", "tier": "hard", "title": "Sort by digit sum, ties descending",
        "params": [{"name": "xs", "type": "list[int]", "min": 0, "max": 999, "max_len": 12}],
        "returns": "list[int]", "description": "", "impl": digit_sum_sort,
        "tests": cases(digit_sum_sort, [[]], [[5]], [[10, 1]], [[1, 10, 100]], [[19, 28, 37, 2]],
                       [[999, 0, 500, 5]], [[11, 2, 20, 101]], [[3, 30, 12, 21, 111]],
                       [[45, 54, 9, 18, 90]], [[7, 7, 16, 25]]),
    },
    # --- extreme ---
    {
        "id": "f22", "tier": "extreme", "title": "Elementary cellular automaton (rule 110, wrapping)",
        "params": [{"name": "cells", "type": "str", "max_len": 24},
                   {"name": "steps", "type": "int", "min": 0, "max": 12}],
        "returns": "str", "description": "", "raises": True, "impl": cellular,
        "tests": cases(cellular, ["", 3], ["1", 1], ["0000", 5], ["0001000", 1], ["0001000", 3],
                       ["1111", 2], ["101010", 1], ["0000000000000001", 12],
                       ["110100111", 4], ["010", 0], ["100000000000000000000000", 7]),
    },
    {
        "id": "f23", "tier": "extreme", "title": "Hidden four-state machine over a, b, c",
        "params": [{"name": "s", "type": "str", "max_len": 30}],
        "returns": "int", "description": "", "raises": True, "impl": hidden_machine,
        "tests": cases(hidden_machine, [""], ["a"], ["ab"], ["abc"], ["cab"], ["ccc"],
                       ["bbbb"], ["abacabac"], ["cbacba"], ["aaaaaaaaaa"],
                       ["abcabcabcabc"], ["cacbcbab"]),
    },
    {
        "id": "f24", "tier": "extreme", "title": "Three regions of (a, b)",
        "params": [{"name": "a", "type": "int", "min": 0, "max": 200},
                   {"name": "b", "type": "int", "min": 0, "max": 200}],
        "returns": "int", "description": "", "impl": regions,
        "tests": cases(regions, [0, 0], [5, 5], [11, 11], [200, 200], [10, 3], [200, 199],
                       [97, 2], [3, 10], [0, 200], [150, 151], [64, 1], [1, 64]),
    },
    {
        "id": "f25", "tier": "extreme", "title": "Word rules: odd reversed, even capped, sorted by length",
        "params": [{"name": "s", "type": "str", "max_len": 60}],
        "returns": "str", "description": "", "impl": word_rules,
        "tests": cases(word_rules, [""], ["a"], ["ab"], ["hello"], ["abcd efg"],
                       ["the quick brown fox"], ["  spaced   out  "], ["zz y xxx wwww"],
                       ["Mixed CASE words"], ["one two three four five"], ["12 345 6789"]),
    },
]
