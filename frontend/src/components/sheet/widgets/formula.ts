/**
 * Formula grammar for computed sheet widgets — mirrors
 * backend/src/loregraph/schemas/formula.py's grammar exactly (kept in sync
 * by hand; both sides carry the same example table in their tests). The
 * backend only *validates* a formula at template-save time; this module is
 * the one place that actually *evaluates* one, against a live entity's
 * field values, for display in a filled-in sheet.
 *
 * Grammar (EBNF):
 *   expr           := ternary
 *   ternary        := logic_or ( "?" expr ":" expr )?
 *   logic_or       := logic_and ( "||" logic_and )*
 *   logic_and      := equality ( "&&" equality )*
 *   equality       := comparison ( ("==" | "!=") comparison )*
 *   comparison     := additive ( ("<" | "<=" | ">" | ">=") additive )*
 *   additive       := multiplicative ( ("+" | "-") multiplicative )*
 *   multiplicative := unary ( ("*" | "/" | "%") unary )*
 *   unary          := ("!" | "-")? primary
 *   primary        := NUMBER | IDENT | "(" expr ")" | IDENT "(" (expr ("," expr)*)? ")"
 *
 * `IDENT` not immediately followed by `(` is a field-key reference; `IDENT(`
 * is a call to one of ALLOWED_FUNCTIONS.
 */

export const ALLOWED_FUNCTIONS = new Set([
  "floor",
  "ceil",
  "round",
  "min",
  "max",
  "abs",
]);

const OPERATORS = [
  "<=",
  ">=",
  "==",
  "!=",
  "&&",
  "||",
  "?",
  ":",
  "<",
  ">",
  "+",
  "-",
  "*",
  "/",
  "%",
  "!",
  "(",
  ")",
  ",",
] as const;

export class FormulaSyntaxError extends Error {}

interface Token {
  kind: "number" | "ident" | "op" | "end";
  value: string;
}

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let pos = 0;
  const length = source.length;
  while (pos < length) {
    const ch = source[pos];
    if (/\s/.test(ch)) {
      pos += 1;
      continue;
    }
    if (/[0-9]/.test(ch)) {
      const start = pos;
      while (pos < length && /[0-9]/.test(source[pos])) pos += 1;
      if (source[pos] === "." && /[0-9]/.test(source[pos + 1] ?? "")) {
        pos += 1;
        while (pos < length && /[0-9]/.test(source[pos])) pos += 1;
      }
      tokens.push({ kind: "number", value: source.slice(start, pos) });
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      const start = pos;
      while (pos < length && /[A-Za-z0-9_]/.test(source[pos])) pos += 1;
      tokens.push({ kind: "ident", value: source.slice(start, pos) });
      continue;
    }
    const op = OPERATORS.find((candidate) => source.startsWith(candidate, pos));
    if (op === undefined) {
      throw new FormulaSyntaxError(
        `unexpected character ${JSON.stringify(ch)} at position ${pos}`,
      );
    }
    tokens.push({ kind: "op", value: op });
    pos += op.length;
  }
  tokens.push({ kind: "end", value: "" });
  return tokens;
}

export type FormulaNode =
  | { type: "num"; value: number }
  | { type: "ident"; name: string }
  | { type: "unary"; op: "!" | "-"; arg: FormulaNode }
  | { type: "binary"; op: string; left: FormulaNode; right: FormulaNode }
  | { type: "ternary"; cond: FormulaNode; then: FormulaNode; else: FormulaNode }
  | { type: "call"; name: string; args: FormulaNode[] };

class Parser {
  private pos = 0;
  private readonly tokens: Token[];

  constructor(tokens: Token[]) {
    this.tokens = tokens;
  }

  private peek(): Token {
    return this.tokens[this.pos];
  }

  private advance(): Token {
    return this.tokens[this.pos++];
  }

  private atOp(op: string): boolean {
    const token = this.peek();
    return token.kind === "op" && token.value === op;
  }

  private expectOp(op: string): void {
    if (!this.atOp(op)) {
      throw new FormulaSyntaxError(
        `expected ${JSON.stringify(op)}, found ${JSON.stringify(this.peek().value)}`,
      );
    }
    this.advance();
  }

  parse(): FormulaNode {
    const node = this.expr();
    if (this.peek().kind !== "end") {
      throw new FormulaSyntaxError(
        `unexpected trailing token ${JSON.stringify(this.peek().value)}`,
      );
    }
    return node;
  }

  private expr(): FormulaNode {
    return this.ternary();
  }

  private ternary(): FormulaNode {
    const cond = this.logicOr();
    if (this.atOp("?")) {
      this.advance();
      const then = this.expr();
      this.expectOp(":");
      const elseBranch = this.expr();
      return { type: "ternary", cond, then, else: elseBranch };
    }
    return cond;
  }

  private binaryLevel(next: () => FormulaNode, ops: readonly string[]): FormulaNode {
    let node = next();
    while (this.peek().kind === "op" && ops.includes(this.peek().value)) {
      const op = this.advance().value;
      const right = next();
      node = { type: "binary", op, left: node, right };
    }
    return node;
  }

  private logicOr = (): FormulaNode => this.binaryLevel(this.logicAnd, ["||"]);
  private logicAnd = (): FormulaNode => this.binaryLevel(this.equality, ["&&"]);
  private equality = (): FormulaNode =>
    this.binaryLevel(this.comparison, ["==", "!="]);
  private comparison = (): FormulaNode =>
    this.binaryLevel(this.additive, ["<", "<=", ">", ">="]);
  private additive = (): FormulaNode =>
    this.binaryLevel(this.multiplicative, ["+", "-"]);
  private multiplicative = (): FormulaNode =>
    this.binaryLevel(this.unary, ["*", "/", "%"]);

  private unary = (): FormulaNode => {
    const token = this.peek();
    if (token.kind === "op" && (token.value === "!" || token.value === "-")) {
      this.advance();
      return { type: "unary", op: token.value, arg: this.unary() };
    }
    return this.primary();
  };

  private primary(): FormulaNode {
    const token = this.advance();
    if (token.kind === "number") {
      return { type: "num", value: Number(token.value) };
    }
    if (token.kind === "ident") {
      if (this.atOp("(")) {
        if (!ALLOWED_FUNCTIONS.has(token.value)) {
          throw new FormulaSyntaxError(`unknown function ${JSON.stringify(token.value)}`);
        }
        this.advance();
        const args: FormulaNode[] = [];
        if (!this.atOp(")")) {
          args.push(this.expr());
          while (this.atOp(",")) {
            this.advance();
            args.push(this.expr());
          }
        }
        this.expectOp(")");
        return { type: "call", name: token.value, args };
      }
      return { type: "ident", name: token.value };
    }
    if (token.kind === "op" && token.value === "(") {
      const node = this.expr();
      this.expectOp(")");
      return node;
    }
    throw new FormulaSyntaxError(`unexpected token ${JSON.stringify(token.value)}`);
  }
}

export function parseFormula(formula: string): FormulaNode {
  if (!formula.trim()) {
    throw new FormulaSyntaxError("formula must not be empty");
  }
  return new Parser(tokenize(formula)).parse();
}

export function parseDependencies(formula: string): Set<string> {
  const deps = new Set<string>();
  const walk = (node: FormulaNode): void => {
    switch (node.type) {
      case "ident":
        deps.add(node.name);
        return;
      case "unary":
        walk(node.arg);
        return;
      case "binary":
        walk(node.left);
        walk(node.right);
        return;
      case "ternary":
        walk(node.cond);
        walk(node.then);
        walk(node.else);
        return;
      case "call":
        node.args.forEach(walk);
        return;
      case "num":
        return;
    }
  };
  walk(parseFormula(formula));
  return deps;
}

function toNumber(value: unknown): number {
  if (typeof value === "boolean") return value ? 1 : 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function toBool(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  return toNumber(value) !== 0;
}

function callFunction(name: string, args: number[]): number {
  switch (name) {
    case "floor":
      return Math.floor(args[0]);
    case "ceil":
      return Math.ceil(args[0]);
    case "round":
      return Math.round(args[0]);
    case "abs":
      return Math.abs(args[0]);
    case "min":
      return Math.min(...args);
    case "max":
      return Math.max(...args);
    default:
      // Unreachable: parseFormula rejects any name outside ALLOWED_FUNCTIONS.
      return 0;
  }
}

function evaluateNode(
  node: FormulaNode,
  values: Record<string, unknown>,
): number | boolean {
  switch (node.type) {
    case "num":
      return node.value;
    case "ident":
      return values[node.name] as number | boolean | undefined ?? 0;
    case "unary": {
      const arg = evaluateNode(node.arg, values);
      return node.op === "!" ? !toBool(arg) : -toNumber(arg);
    }
    case "call":
      return callFunction(
        node.name,
        node.args.map((arg) => toNumber(evaluateNode(arg, values))),
      );
    case "ternary":
      return toBool(evaluateNode(node.cond, values))
        ? evaluateNode(node.then, values)
        : evaluateNode(node.else, values);
    case "binary": {
      if (node.op === "&&") {
        return toBool(evaluateNode(node.left, values)) && toBool(evaluateNode(node.right, values));
      }
      if (node.op === "||") {
        return toBool(evaluateNode(node.left, values)) || toBool(evaluateNode(node.right, values));
      }
      const left = toNumber(evaluateNode(node.left, values));
      const right = toNumber(evaluateNode(node.right, values));
      switch (node.op) {
        case "+":
          return left + right;
        case "-":
          return left - right;
        case "*":
          return left * right;
        case "/":
          return right === 0 ? 0 : left / right;
        case "%":
          return right === 0 ? 0 : left % right;
        case "==":
          return left === right;
        case "!=":
          return left !== right;
        case "<":
          return left < right;
        case "<=":
          return left <= right;
        case ">":
          return left > right;
        case ">=":
          return left >= right;
        default:
          return 0;
      }
    }
  }
}

/** Missing/unresolvable field keys evaluate to 0/false — an entity can be
 * only partially filled in, so a computed widget must degrade, not throw. */
export function evaluateFormula(
  formula: string,
  values: Record<string, unknown>,
): number | boolean {
  return evaluateNode(parseFormula(formula), values);
}
