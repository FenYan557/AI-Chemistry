# -*- coding: utf-8 -*-
"""共享文本归一（阶段一与阶段二唯一依赖）。

设计要点（针对审查意见 P1-2）：
  1. **绝不静默删除未知命令**：认不出的 \\cmd 原样保留并登记到 flags["unmapped"]
  2. **上下标不拼成数字**：`10^{2}` → `10^2`（不是 `102`），`10^{-14}` → `10^-14`
  3. 希腊字母/算符 → Unicode，仅限可确定映射的
  4. 显示与索引分离：display 保留 `^`/`_` 与符号；index 进一步压成 ASCII 供检索
"""
from __future__ import annotations

import re
import unicodedata

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ",
    "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ",
    "Theta": "Θ", "kappa": "κ", "lambda": "λ", "Lambda": "Λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "Sigma": "Σ",
    "tau": "τ", "phi": "φ", "varphi": "φ", "Phi": "Φ", "chi": "χ", "psi": "ψ",
    "omega": "ω", "Omega": "Ω",
}
OPS = {
    "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "approx": "≈", "sim": "~",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "infty": "∞",
    "partial": "∂", "nabla": "∇", "rightarrow": "→", "to": "→", "propto": "∝",
    "circ": "°", "degree": "°", "percent": "%", "dots": "…", "ldots": "…",
    "sum": "Σ", "prod": "Π", "int": "∫", "bullet": "•", "prime": "′",
    "leftrightarrow": "↔", "Leftrightarrow": "⇔", "Rightarrow": "⇒",
    "rightleftharpoons": "⇌", "nu": "ν", "Nu": "Ν", "ell": "ℓ",
}
# 只去壳、不改语义的结构命令
WRAP = {"mathrm", "mathbf", "mathsf", "mathit", "mathnormal", "text", "textrm",
        "textbf", "textit", "left", "right", "big", "Big", "bigl", "bigr",
        "displaystyle", "scriptstyle", "quad", "qquad", "hspace", "vspace",
        "mathfrak", "mathtt", "mathcal", "mathbb", "boldsymbol", "bf", "sf",
        "operatorname", "bar", "dot", "hat", "tilde", "vec", "mathring",
        "overline", "underline", "mathrm", "mathit"}
FRAC = {"frac", "dfrac", "tfrac", "nicefrac"}
TAG = re.compile(r"\\tag\*?\{([^{}]{1,8})\}")
CMD = re.compile(r"\\([a-zA-Z]+)")
SUP = re.compile(r"\^\s*\{([^{}]*)\}|\^\s*(\S)")
SUB = re.compile(r"_\s*\{([^{}]*)\}|_\s*(\S)")


def _shell(s: str) -> str:
    s = s.replace("$$", " ").replace("$", " ")
    s = s.replace("\\%", "%").replace("\\_", "_").replace("\\&", "&").replace("\\#", "#")
    return s


def _merge_letter_runs(t: str) -> str:
    """MinerU 会把分子式拆成 'C u S O'、'A g N P s'：把 ≥3 个连续单字母合起来。"""
    return re.sub(r"(?<![A-Za-z])(?:[A-Za-z]\s){2,}[A-Za-z](?![A-Za-z])",
                  lambda m: m.group(0).replace(" ", ""), t)


def latex_to_display(s: str) -> tuple[str, dict]:
    """LaTeX 片段 → 可读文本。返回 (text, flags)。"""
    flags: dict = {}
    t = _shell(s or "")
    t = TAG.sub(lambda m: f" (Eq.{m.group(1)})", t)

    # 上下标：保留 ^ / _ 结构，不拼数字
    t = SUP.sub(lambda m: "^" + (m.group(1) or m.group(2)), t)
    t = SUB.sub(lambda m: "_" + (m.group(1) or m.group(2)), t)

    # MinerU 常在花括号里把字母逐个用空格拆开：\mathrm { F e } → 先合起来
    def unwrap(m: re.Match) -> str:
        body = m.group(1)
        toks = body.split()
        if len(toks) >= 2 and all(len(x) <= 2 for x in toks):
            body = "".join(toks)
        return " " + body + " "

    t = re.sub(r"\\(?:mathrm|mathbf|mathsf|mathit|operatorname|text)\s*\{([^{}]*)\}", unwrap, t)

    unmapped: list[str] = []

    def cmd(m: re.Match) -> str:
        name = m.group(1)
        if name in GREEK:
            return GREEK[name]
        if name in OPS:
            return OPS[name]
        if name in WRAP:
            return ""
        if name in FRAC:
            flags["has_frac"] = True
            return " "          # 分式：交给上一级决定是否整体保 LaTeX
        unmapped.append(m.group(0))
        return m.group(0)       # 不删，原样保留

    t = CMD.sub(cmd, t)
    t = t.replace("{", "").replace("}", "")
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", t)   # 0. 005 → 0.005
    t = _merge_letter_runs(t)
    t = re.sub(r"\s+([,.;:)])", r"\1", t).strip()
    if unmapped:
        flags["unmapped"] = sorted(set(unmapped))[:8]
        flags["unmapped_n"] = len(unmapped)
    return t, flags


INDEX_MAP = {"Δ": "D", "δ": "d", "η": "n", "λ": "l", "σ": "s", "θ": "t", "ω": "w",
             "Ω": "O", "µ": "u", "μ": "u", "−": "-", "–": "-", "—": "-", "·": " ",
             "×": "x", "≥": ">=", "≤": "<=", "±": "+-", "％": "%", "℃": "C",
             "α": "a", "β": "b", "γ": "g", "ρ": "r", "φ": "p", "φ": "p", "κ": "k",
             "∂": "d", "∇": "grad", "∞": "inf", "→": "->", "≈": "~"}


def to_index(s: str) -> str:
    """检索用 ASCII 归一：先剥 LaTeX 命令名（无检索价值），再符号→ASCII、NFKC、压空白。"""
    t = CMD.sub("", s or "")
    for k, v in INDEX_MAP.items():
        t = t.replace(k, v)
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[^\w\s/\.\-\+%\^_]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


UNIT_FIX = [
    (r"mA\s*(?:/|\s)\s*cm\s*(?:-|\^)?\s*2", "mA/cm2"),
    (r"A\s*(?:/|\s)\s*dm\s*(?:-|\^)?\s*2", "A/dm2"),
    (r"mJ\s*(?:/|\s)\s*m\s*(?:-|\^)?\s*2", "mJ/m2"),
    (r"mg\s*(?:/|\s)\s*[lL]\s*(?:-|\^)?\s*1", "mg/L"),
    (r"(?<![a-z])g\s*(?:/|\s)\s*[lL]\s*(?:-|\^)?\s*1", "g/L"),
    (r"mmol\s*(?:/|\s)\s*[lL]\s*(?:-|\^)?\s*1", "mmol/L"),
    (r"(?<!m)mol\s*(?:/|\s)\s*[lL]\s*(?:-|\^)?\s*1", "mol/L"),
]


def norm_units(s: str) -> str:
    t = s
    for pat, rep in UNIT_FIX:
        t = re.sub(pat, rep, t)
    t = t.replace("℃", "°C").replace("º", "°")
    return re.sub(r"\s{2,}", " ", t)


def norm_text(s: str) -> tuple[str, str, dict]:
    """一步到位：返回 (display, index, flags)。"""
    disp, flags = latex_to_display(s)
    disp = norm_units(disp)
    disp = re.sub(r"\s{2,}", " ", disp).strip()
    return disp, to_index(disp), flags
