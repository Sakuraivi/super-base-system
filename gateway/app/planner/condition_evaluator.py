"""Safe expression evaluator for DAG condition nodes.

Uses Python's ast module to parse and evaluate simple expressions
against execution context, without allowing arbitrary code execution.
"""
from __future__ import annotations

import ast
import operator
from typing import Any


class ConditionEvalError(Exception):
    """Raised when a condition expression cannot be safely evaluated."""


# Supported comparison operators
_CMP_OPS: dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# Supported boolean operators
_BOOL_OPS: dict[type, Any] = {
    ast.And: lambda values: all(values),
    ast.Or: lambda values: any(values),
}

# Custom comparator name for "contains"
_CONTAINS_CMP = "contains"


class _SafeEvaluator(ast.NodeVisitor):
    """Walk an AST expression and evaluate it against a variable context.

    Only allows: Compare, BoolOp, UnaryOp(not), Constant, Name, Attribute,
    List, Tuple, Set, Dict. Everything else raises ConditionEvalError.
    """

    def __init__(self, variables: dict[str, Any]):
        self._variables = variables

    def _resolve_name(self, node: ast.expr) -> Any:
        """Resolve an ast.Attribute/ast.Name chain to a value."""
        if isinstance(node, ast.Name):
            name = node.id
            if name not in self._variables:
                raise ConditionEvalError(f"Undefined variable: {name}")
            return self._variables[name]
        if isinstance(node, ast.Attribute):
            base = self._resolve_name(node.value)
            attr = node.attr
            if isinstance(base, dict):
                if attr not in base:
                    raise ConditionEvalError(f"Key '{attr}' not found")
                return base[attr]
            if hasattr(base, attr):
                return getattr(base, attr)
            raise ConditionEvalError(f"Attribute '{attr}' not found on {type(base).__name__}")
        raise ConditionEvalError(f"Unsupported name expression: {type(node).__name__}")

    def evaluate(self, node: ast.expr) -> Any:
        return self.visit(node)

    # ── Node visitors ───────────────────────────────────────────────

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        return self._resolve_name(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        return self._resolve_name(node)

    def visit_List(self, node: ast.List) -> list:
        return [self.visit(elt) for elt in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple:
        return tuple(self.visit(elt) for elt in node.elts)

    def visit_Set(self, node: ast.Set) -> set:
        return {self.visit(elt) for elt in node.elts}

    def visit_Dict(self, node: ast.Dict) -> dict:
        return {self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values)}

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        op_type = type(node.op)
        if op_type not in _BOOL_OPS:
            raise ConditionEvalError(f"Unsupported boolean operator: {op_type.__name__}")
        fn = _BOOL_OPS[op_type]
        return fn([self.visit(v) for v in node.values])

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        if isinstance(node.op, ast.Not):
            return not self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            val = self.visit(node.operand)
            if not isinstance(val, (int, float)):
                raise ConditionEvalError("USub only supported on numbers")
            return -val
        raise ConditionEvalError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            op_type = type(op)

            # Special handling for "contains" (rewritten from "X contains Y")
            # This is handled via a synthetic comparator injected during parsing
            if op_type is ast.In:
                # "left in right" → left in right
                if not self._cmp_eval(left, right, op_type):
                    return False
            elif op_type in _CMP_OPS:
                if not self._cmp_eval(left, right, op_type):
                    return False
            else:
                raise ConditionEvalError(f"Unsupported comparator: {op_type.__name__}")
            left = right
        return True

    def _cmp_eval(self, left: Any, right: Any, op_type: type) -> bool:
        fn = _CMP_OPS.get(op_type)
        if fn is None:
            raise ConditionEvalError(f"Unsupported comparator: {op_type.__name__}")
        return fn(left, right)

    def visit_Call(self, node: ast.Call) -> None:
        raise ConditionEvalError("Function calls are not allowed in conditions")

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        base = self.visit(node.value)
        key = self.visit(node.slice)
        if isinstance(base, dict):
            return base[key]
        if isinstance(base, (list, tuple)):
            return base[key]
        raise ConditionEvalError(f"Subscript not supported on {type(base).__name__}")

    def generic_visit(self, node: ast.AST) -> None:
        raise ConditionEvalError(f"Unsupported AST node: {type(node).__name__}")


def _rewrite_contains_expr(expr: str) -> str:
    """Rewrite 'X contains Y' syntax into a supported form.

    Since Python's `in` keyword is "Y in X" but our DSL uses "X contains Y",
    we do a simple text transformation for the common case.
    """
    # Handle: expr contains literal  OR  expr contains expr
    # We rewrite to: (literal) in (expr) by using ast transformation
    # Actually, simpler: we parse normally and handle `contains` as a special
    # comparator name. But Python's AST doesn't know "contains".
    # Solution: rewrite "X contains Y" → "Y in X" at the string level.
    import re
    # Match: <expr> contains <expr>
    # This is tricky with nested expressions, so we do a simple approach:
    # split on " contains " and rebuild as "right in left"
    # Only handle top-level "contains" (not inside parens for simplicity)
    if " contains " in expr:
        parts = expr.split(" contains ", 1)
        left_str = parts[0].strip()
        right_str = parts[1].strip()
        return f"({right_str}) in ({left_str})"
    return expr


def _build_variables(context: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """Build the variable namespace for expression evaluation."""
    variables: dict[str, Any] = {}
    # ctx.* → context values
    variables["ctx"] = context
    # results.* → execution results
    variables["results"] = results
    # Also allow direct access to top-level context keys
    for key, val in context.items():
        variables[key] = val
    return variables


class ConditionEvaluator:
    """Evaluate condition expressions against execution context.

    Supported syntax:
        ctx.score > 80
        ctx.status == 'active'
        ctx.age > 18 and ctx.verified == True
        ctx.tags contains 'urgent'  (rewritten to 'urgent' in ctx.tags)
        ctx.role in ['admin', 'editor']
        not ctx.disabled
        results.node_1.status == 'completed'
    """

    @staticmethod
    def evaluate(
        expression: str,
        context: dict[str, Any],
        results: dict[str, Any],
    ) -> bool:
        if not expression or not expression.strip():
            raise ConditionEvalError("Empty condition expression")

        # Rewrite "contains" syntax
        rewritten = _rewrite_contains_expr(expression.strip())

        try:
            tree = ast.parse(rewritten, mode="eval")
        except SyntaxError as e:
            raise ConditionEvalError(f"Syntax error in expression: {e}") from e

        variables = _build_variables(context, results)
        evaluator = _SafeEvaluator(variables)

        try:
            result = evaluator.evaluate(tree.body)
        except ConditionEvalError:
            raise
        except Exception as e:
            raise ConditionEvalError(f"Evaluation error: {e}") from e

        return bool(result)
