"""Amounts of the inventory as formulas of the modelling choices, for openLCA.

The builder writes each amount as ordinary Python arithmetic on the values of the choices.
Running that same arithmetic on symbols instead of numbers gives the formula of every amount,
so the model that goes to openLCA can keep the choices as parameters that drive the exchanges:
a person can change a parameter in openLCA, or let openLCA's Monte Carlo simulation draw it.

Only continuous choices become symbols. A categorical choice selects a dataset or a route; it
stays fixed at the option of the world that is sent, because an openLCA parameter is a number.
Only + - * / are traced: an amount that needs anything else keeps its number, and `trace`
reports it.
"""
import ast
import logging
import operator
from decimal import Decimal

log = logging.getLogger(__name__)


def number(x):
    """A number as openLCA's formula parser reads it: plain decimals, no exponent."""
    x = float(x)
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return format(Decimal(repr(x)), "f")


class Sym:
    """A value that remembers how it was computed."""

    __slots__ = ("text", "value", "atom")

    def __init__(self, text, value, atom=True):
        self.text, self.value, self.atom = text, float(value), atom

    @staticmethod
    def _of(x):
        if isinstance(x, Sym):
            return x
        v = float(x)
        return Sym(number(v) if v >= 0 else f"({number(v)})", v)

    def _wrap(self):
        return self.text if self.atom else f"({self.text})"

    def _op(self, other, op, value, swap=False):
        if not isinstance(other, Sym):          # leave out what changes nothing: x * 1, x / 1, x + 0, x - 0
            k = float(other)
            if (op == "*" and k == 1.0) or (op == "/" and k == 1.0 and not swap) \
                    or (op == "+" and k == 0.0) or (op == "-" and k == 0.0 and not swap):
                return self
        a, b = (Sym._of(other), self) if swap else (self, Sym._of(other))
        return Sym(f"{a._wrap()} {op} {b._wrap()}", value, atom=False)

    def __add__(self, o): return self._op(o, "+", self.value + float(o))
    def __radd__(self, o): return self._op(o, "+", float(o) + self.value, swap=True)
    def __sub__(self, o): return self._op(o, "-", self.value - float(o))
    def __rsub__(self, o): return self._op(o, "-", float(o) - self.value, swap=True)
    def __mul__(self, o): return self._op(o, "*", self.value * float(o))
    def __rmul__(self, o): return self._op(o, "*", float(o) * self.value, swap=True)
    def __truediv__(self, o): return self._op(o, "/", self.value / float(o))
    def __rtruediv__(self, o): return self._op(o, "/", float(o) / self.value, swap=True)
    def __neg__(self): return Sym(f"-{self._wrap()}", -self.value, atom=False)
    def __pos__(self): return self
    def __float__(self): return self.value


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def evaluate(text, env):
    """The value of a formula written by Sym: numbers, parameter names, + - * / and brackets.

    Not Python's eval: anything else in the text (a call, an attribute, a power) is refused, so a
    formula can never run code, whatever a parameter name or a product file contains."""
    def value(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            return float(env[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](value(node.left), value(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -value(node.operand)
        raise ValueError(f"not a formula of BRANCH: {ast.dump(node)}")
    return value(ast.parse(text, mode="eval").body)


def _agree(traced, numbers):
    return set(traced) == set(numbers) and all(
        abs(float(traced[k]) - float(numbers[k])) <= 1e-9 * max(1e-12, abs(float(numbers[k]))) for k in numbers)


def _holds_elsewhere(term, traced, plain, names):
    """The formulas must give the amounts of the term at another world too: an amount that turned a
    choice into a constant on the way agrees at the traced world and nowhere else."""
    moved = {d: (v * 1.07 if d in names else v) for d, v in plain.items()}
    try:
        numbers = term.inventory(moved)
    except Exception as exc:             # a term may refuse a world for any reason of its own
        log.debug("%s cannot be evaluated at the moved world, so nothing is compared there: %s", term.name, exc)
        return True
    env = {names[d]: moved[d] for d in moved if d in names}
    values = {k: (evaluate(a.text, env) if isinstance(a, Sym) else float(a)) for k, a in traced.items()}
    return _agree(values, numbers)


def trace(model, world, names):
    """Inventory of one world with formulas.

    names   {choice name: parameter name} for the continuous choices to keep as parameters
    Returns ({label: {factor key: (amount, formula or None)}}, [choices that could not be traced]).
    The formula of a key is the sum over the terms that use it; None when no parameter enters it.
    """
    out = {model.label_a: {}, model.label_b: {}}
    failed = set()
    for t in model.terms:
        if t.inventory is None:
            raise ValueError(f"Term {t.name} has no inventory; build the model with builder.py")
        side = out[model.label_a if t.sign > 0 else model.label_b]
        plain = {d: float(world[d]) for d in t.deps}
        numbers = t.inventory(plain)
        symbolic = {d: (Sym(names[d], world[d]) if d in names else float(world[d])) for d in t.deps}
        try:
            traced = t.inventory(symbolic)
            ok = _agree(traced, numbers) and _holds_elsewhere(t, traced, plain, names)
        except Exception as exc:         # an operation the symbols do not have: the amount stays a number
            log.debug("the formula of %s could not be written: %s", t.name, exc)
            ok = False
        if not ok:
            failed.update(d for d in t.deps if d in names)
            traced = numbers
        for key, amount in traced.items():
            value, text = side.get(key, (0.0, None))
            part = amount.text if isinstance(amount, Sym) else None
            if isinstance(amount, Sym) and not amount.atom:
                part = f"({part})"
            if part is None and text is not None and float(amount) != 0.0:
                part = Sym._of(float(amount)).text
            elif part is not None and text is None and value != 0.0:
                text = Sym._of(value).text
            side[key] = (value + float(amount), text if part is None else part if text is None else f"{text} + {part}")
    return out, sorted(failed)
