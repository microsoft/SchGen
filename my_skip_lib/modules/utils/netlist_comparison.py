# Deisgned to compare two netlists
import re
from typing import Any, List, Tuple, Dict, Set

# ============
# S-expression parser (minimal, zero dependency)
# ============

def _tokenize_sexpr(s: str) -> List[str]:
    """
    Tokenize a KiCad netlist S-expression into a list of tokens.
    Supports parentheses, strings in double quotes, and atoms.
    """
    tokens = []
    i, n = 0, len(s)
    WHITESPACE = set(" \t\r\n")
    while i < n:
        c = s[i]
        if c in WHITESPACE:
            i += 1
            continue
        if c in ("(", ")"):
            tokens.append(c)
            i += 1
            continue
        if c == '"':
            # parse quoted string (supports simple escaping of \")
            i += 1
            buf = []
            while i < n:
                if s[i] == '\\' and i + 1 < n:
                    # keep escaped char
                    buf.append(s[i+1])
                    i += 2
                    continue
                if s[i] == '"':
                    i += 1
                    break
                buf.append(s[i])
                i += 1
            tokens.append('"' + "".join(buf) + '"')
            continue
        # atom
        j = i
        while j < n and s[j] not in WHITESPACE and s[j] not in ("(", ")"):
            j += 1
        tokens.append(s[i:j])
        i = j
    return tokens

def _parse_tokens(tokens: List[str], pos: int = 0) -> Tuple[Any, int]:
    """
    Recursive descent parser for S-expressions.
    Returns (node, next_pos).
    Node is either a string atom or a list [ ... ].
    """
    result = []
    n = len(tokens)
    while pos < n:
        t = tokens[pos]
        if t == "(":
            node, pos = _parse_tokens(tokens, pos + 1)
            result.append(node)
        elif t == ")":
            return result, pos + 1
        else:
            # normalize atoms: strip quotes if present
            if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
                result.append(t[1:-1])
            else:
                result.append(t)
            pos += 1
    # if we reach here, parentheses might be unbalanced; return what we have
    return result, pos

def parse_sexpr(s: str) -> List[Any]:
    """Convenience wrapper: tokenize and parse, returning a list (top-level)."""
    tokens = _tokenize_sexpr(s)
    ast, _ = _parse_tokens(tokens, 0)
    # Ensure top-level is a list
    if not isinstance(ast, list):
        ast = [ast]
    return ast

# ============
# KiCad netlist extraction
# ============

def _find_first_block(ast: List[Any], head: str) -> List[Any]:
    """
    Find the first list whose first atom equals 'head', e.g., 'nets'.
    Returns the list node, or [] if not found.
    """
    for node in ast:
        if isinstance(node, list) and node:
            if isinstance(node[0], str) and node[0] == head:
                return node
            # search recursively
            sub = _find_first_block(node, head)
            if sub:
                return sub
    return []

def _children_by_head(block: List[Any], head: str) -> List[List[Any]]:
    """
    From a list node, return direct children lists that start with 'head'.
    """
    out = []
    for node in block[1:]:
        if isinstance(node, list) and node and isinstance(node[0], str) and node[0] == head:
            out.append(node)
    return out

def _get_kv(block: List[Any], key: str) -> List[Any]:
    """
    Return all direct child lists that start with key, e.g., (name "...").
    """
    out = []
    for node in block[1:]:
        if isinstance(node, list) and node and node[0] == key:
            out.append(node)
    return out

def extract_net_tuples(kicad_netlist_text: str) -> Set[Tuple[str, str, str]]:
    """
    Extract a structural set of (net_name, ref, pin) tuples from a KiCad S-expression netlist.
    This ignores line order and whitespace and is robust to formatting differences.
    """
    # Optional light cleanup: KiCad uses {slash} in net names; standardize it to '/' for comparison
    text = kicad_netlist_text.replace("{slash}", "/")

    ast = parse_sexpr(text)
    nets_block = _find_first_block(ast, "nets")
    if not nets_block:
        return set()

    tuples: Set[Tuple[str, str, str]] = set()
    for net in _children_by_head(nets_block, "net"):
        # (net (code "...") (name "...") (node ...) (node ...))
        name_nodes = _get_kv(net, "name")
        net_name = None
        if name_nodes and len(name_nodes[0]) >= 2:
            net_name = str(name_nodes[0][1]).strip()
        else:
            # Fallback: try to derive a name-like identifier
            net_name = "UNKNOWN"

        # collect node entries
        for node in _children_by_head(net, "node"):
            # (node (ref "U2") (pin "24") ...)
            ref = pin = None
            for child in node[1:]:
                if isinstance(child, list) and child:
                    if child[0] == "ref" and len(child) >= 2:
                        ref = str(child[1]).strip()
                    if child[0] == "pin" and len(child) >= 2:
                        pin = str(child[1]).strip()
            if ref and pin:
                tuples.add((net_name, ref, pin))
    return tuples

# ============
# Similarity metrics
# ============

def jaccard_similarity(set_a: Set[Tuple[str, str, str]], set_b: Set[Tuple[str, str, str]]) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0

def precision_recall_f1(set_true: Set[Tuple[str, str, str]], set_pred: Set[Tuple[str, str, str]]) -> Tuple[float, float, float]:
    """
    Compute Precision/Recall/F1 where set_true is the reference (A) and set_pred is the candidate (B).
    """
    tp = len(set_true & set_pred)
    p = tp / len(set_pred) if set_pred else 0.0
    r = tp / len(set_true) if set_true else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
    return p, r, f1

def compare_kicad_netlists(text_a: str, text_b: str) -> Dict[str, float]:
    """
    Parse two KiCad netlists and compute structural similarity metrics on (net, ref, pin) tuples.
    Returns a dict including sizes, intersection, Jaccard, Precision/Recall/F1.
    """
    A = extract_net_tuples(text_a)
    B = extract_net_tuples(text_b)

    j = jaccard_similarity(A, B)
    p, r, f1 = precision_recall_f1(A, B)

    return {
        "A_size": float(len(A)),
        "B_size": float(len(B)),
        "intersection": float(len(A & B)),
        "jaccard": j,
        "precision_A->B": p,  # of B against A
        "recall_A->B": r,     # of A recovered by B
        "f1_A->B": f1,
    }