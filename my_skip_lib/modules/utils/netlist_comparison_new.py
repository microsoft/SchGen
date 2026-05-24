from typing import Any, List, Tuple, Dict, Set, FrozenSet, Optional

# -----------------------------
# Minimal S-expression utilities
# -----------------------------

def _tokenize_sexpr(s: str) -> List[str]:
    tokens, i, n = [], 0, len(s)
    WHITESPACE = set(" \t\r\n")
    while i < n:
        c = s[i]
        if c in WHITESPACE:
            i += 1; continue
        if c in ("(", ")"):
            tokens.append(c); i += 1; continue
        if c == '"':
            i += 1; buf = []
            while i < n:
                if s[i] == '\\' and i + 1 < n:
                    buf.append(s[i+1]); i += 2; continue
                if s[i] == '"':
                    i += 1; break
                buf.append(s[i]); i += 1
            tokens.append('"' + "".join(buf) + '"'); continue
        j = i
        while j < n and s[j] not in WHITESPACE and s[j] not in ("(", ")"):
            j += 1
        tokens.append(s[i:j]); i = j
    return tokens

def _parse_tokens(tokens: List[str], pos: int = 0) -> Tuple[Any, int]:
    out, n = [], len(tokens)
    while pos < n:
        t = tokens[pos]
        if t == "(":
            node, pos = _parse_tokens(tokens, pos + 1)
            out.append(node)
        elif t == ")":
            return out, pos + 1
        else:
            if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
                out.append(t[1:-1])
            else:
                out.append(t)
            pos += 1
    return out, pos

def parse_sexpr(text: str) -> List[Any]:
    tok = _tokenize_sexpr(text)
    ast, _ = _parse_tokens(tok, 0)
    return ast if isinstance(ast, list) else [ast]

# -----------------------------
# AST helpers
# -----------------------------

def _find_first_block(ast: List[Any], head: str) -> List[Any]:
    for node in ast:
        if isinstance(node, list) and node:
            if node[0] == head:
                return node
            sub = _find_first_block(node, head)
            if sub:
                return sub
    return []

def _children_by_head(block: List[Any], head: str) -> List[List[Any]]:
    out = []
    for node in block[1:]:
        if isinstance(node, list) and node and node[0] == head:
            out.append(node)
    return out

def _first_kv(block: List[Any], key: str) -> str:
    for node in block[1:]:
        if isinstance(node, list) and node and node[0] == key and len(node) >= 2:
            return str(node[1])
    return ""

# -----------------------------
# Build: set of net-sets ({ frozenset({'lib:part:pin', ...}), ... })
# -----------------------------

def build_net_sets_libpart_pin(text: str, keep_singletons: bool = True) -> Set[FrozenSet[str]]:
    """
    For each net, construct a set of tokens 'lib:part:pin' by reverse mapping node.ref
    to its (lib, part) from components/libsource. Return a set of these per-net frozensets.

    Enhancement:
    - Drop dangling/unconnected single-node nets where the net name describes that lone node itself,
      e.g. "unconnected-(C1-Pad1)" or "Net-(J1-Pin_12)".
    """
    text = text.replace("{slash}", "/")
    ast = parse_sexpr(text)

    # ref -> (lib, part)
    ref2lp: Dict[str, Tuple[str, str]] = {}
    comps = _find_first_block(ast, "components")
    if comps:
        for comp in _children_by_head(comps, "comp"):
            ref = _first_kv(comp, "ref")
            lib = part = ""
            for node in comp[1:]:
                if isinstance(node, list) and node and node[0] == "libsource":
                    lib = _first_kv(node, "lib")
                    part = _first_kv(node, "part")
                    break
            if ref and (lib or part):
                ref2lp[ref] = (lib, part)

    def _norm(s: str) -> str:
        # normalize for robust matching
        return "".join(s.strip().lower().split())

    def _extract_net_name(net_block: List[Any]) -> str:
        # (net (code "x") (name "...") ...)
        for node in net_block[1:]:
            if isinstance(node, list) and node and node[0] == "name" and len(node) >= 2:
                return str(node[1])
        return ""

    def _extract_single_node_info(net_block: List[Any]) -> Optional[Tuple[str, str, str]]:
        # return (ref, pin, pinfunction) for the *only* node, else None
        nodes = _children_by_head(net_block, "node")
        if len(nodes) != 1:
            return None

        ref = pin = pinfunction = ""
        node = nodes[0]
        for kv in node[1:]:
            if isinstance(kv, list) and kv:
                if kv[0] == "ref" and len(kv) >= 2:
                    ref = str(kv[1]).strip()
                elif kv[0] == "pin" and len(kv) >= 2:
                    pin = str(kv[1]).strip()
                elif kv[0] == "pinfunction" and len(kv) >= 2:
                    pinfunction = str(kv[1]).strip()
        if not (ref and pin):
            return None
        return ref, pin, pinfunction

    def _is_dangling_single_node_net(net_block: List[Any]) -> bool:
        """
        True if:
        1) net has exactly one node
        2) net name looks like it is describing that node itself (unconnected-/Net-(...))
           AND contains both ref and pin (or pinfunction).
        """
        info = _extract_single_node_info(net_block)
        if info is None:
            return False
        ref, pin, pinfunction = info

        name = _extract_net_name(net_block)
        if not name:
            return False

        name_n = _norm(name)
        ref_n = _norm(ref)
        pin_n = _norm(pin)
        pinfunc_n = _norm(pinfunction) if pinfunction else ""

        # quick gate: these patterns are typical KiCad "dangling" names
        # e.g. unconnected-(C1-Pad1), Net-(J1-Pin_12)
        if not (name_n.startswith("unconnected-(") or name_n.startswith("net-(")):
            return False

        # Must contain ref, and must contain either pin or pinfunction.
        if ref_n not in name_n:
            return False

        # pin can appear as "pad1", "pin12", "pin_12", or just "...-1" in some cases.
        pin_hits = (
            (pin_n and pin_n in name_n) or
            (pin_n and f"pad{pin_n}" in name_n) or
            (pin_n and f"pin{pin_n}" in name_n) or
            (pin_n and f"pin_{pin_n}" in name_n)
        )
        pinfunc_hits = pinfunc_n and (pinfunc_n in name_n)

        return bool(pin_hits or pinfunc_hits)

    # nets -> per-net tokens
    result: Set[FrozenSet[str]] = set()
    nets = _find_first_block(ast, "nets")
    if not nets:
        return result

    for net in _children_by_head(nets, "net"):
        # NEW: drop dangling single-node nets whose name describes itself
        if _is_dangling_single_node_net(net):
            continue

        tokens_this_net: Set[str] = set()
        for node in _children_by_head(net, "node"):
            ref = pin = ""
            for kv in node[1:]:
                if isinstance(kv, list) and kv:
                    if kv[0] == "ref" and len(kv) >= 2:
                        ref = str(kv[1]).strip()
                    elif kv[0] == "pin" and len(kv) >= 2:
                        pin = str(kv[1]).strip()
            if not (ref and pin):
                continue
            lib, part = ref2lp.get(ref, ("", ""))
            if not (lib or part):
                # Strict behavior: skip if lib/part unavailable
                continue
            tokens_this_net.add(f"{lib}:{part}:{pin}")

        if tokens_this_net and (keep_singletons or len(tokens_this_net) >= 2):
            result.add(frozenset(tokens_this_net))

    return result

# -----------------------------
# Metrics on set-of-sets
# -----------------------------

def jaccard_sets(A: Set[FrozenSet[str]], B: Set[FrozenSet[str]]) -> float:
    if not A and not B: return 1.0
    return len(A & B) / len(A | B) if (A or B) else 0.0

def prf1_sets(A: Set[FrozenSet[str]], B: Set[FrozenSet[str]]):
    tp = len(A & B)
    p = tp / len(B) if B else 0.0
    r = tp / len(A) if A else 0.0
    f1 = 2*p*r/(p+r) if (p+r) else 0.0
    return p, r, f1

def compare_netlists_sets(text_a: str, text_b: str, keep_singletons: bool = True):
    A = build_net_sets_libpart_pin(text_a, keep_singletons=keep_singletons)
    B = build_net_sets_libpart_pin(text_b, keep_singletons=keep_singletons)
    j = jaccard_sets(A, B)
    p, r, f1 = prf1_sets(A, B)
    return {
        "nets_A": len(A),
        "nets_B": len(B),
        "matched_nets": len(A & B),
        "jaccard": j,
        "precision_A->B": p,
        "recall_A->B": r,
        "f1_A->B": f1,
    }


# =========================
# Example usage
# =========================
if __name__ == "__main__":
    with open("/home/v-qinpeiluo/workspace/llm4circuit/export/test1.net", "r", encoding="utf-8") as fa:
        A = fa.read()
    with open("/home/v-qinpeiluo/workspace/llm4circuit/export/test2.net", "r", encoding="utf-8") as fb:
        B = fb.read()

    sigA = build_net_sets_libpart_pin(A)
    print(sigA)
    sigB = build_net_sets_libpart_pin(B)
    print(sigB)
    print(f"Unique net-signatures A: {len(sigA)}")
    print(f"Unique net-signatures B: {len(sigB)}")
    print(f"Exact signature matches: {len(sigA & sigB)}")

    metrics = compare_netlists_sets(A, B)
    for k, v in metrics.items():
        if k in ("nets_A", "nets_B", "matched_nets"):
            print(f"{k}: {int(v)}")
        else:
            print(f"{k}: {v:.4f}")
