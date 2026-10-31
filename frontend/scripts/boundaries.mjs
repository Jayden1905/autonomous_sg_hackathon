import ts from "typescript";
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { resolve, dirname, relative, extname } from "node:path";

const root = resolve("src");
const files = [];
function walk(folder) {
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = resolve(folder, entry.name);
    if (entry.isDirectory()) walk(path);
    else if (/\.(tsx?|jsx?)$/.test(path)) files.push(path);
  }
}
walk(root);
const graph = new Map();
const allowed = {
  workspace: [],
  airport: ["workspace"],
  flight: ["workspace"],
  scenarios: ["workspace"],
  preview: ["airport", "flight", "scenarios", "workspace"],
};
const errors = [];
for (const file of files) {
  const owner = relative(root, file).split("/")[0];
  const source = ts.createSourceFile(
    file,
    readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
  );
  const edges = [];
  function inspect(node) {
    const specifier =
      ts.isImportDeclaration(node) || ts.isExportDeclaration(node)
        ? node.moduleSpecifier
        : ts.isCallExpression(node) &&
            node.expression.kind === ts.SyntaxKind.ImportKeyword
          ? node.arguments[0]
          : undefined;
    if (ts.isExportDeclaration(node) && !node.exportClause)
      errors.push(`${file}: wildcard export`);
    if (specifier && ts.isStringLiteral(specifier)) {
      const name = specifier.text;
      if (name.startsWith("@/") || name.startsWith(".")) {
        const base = name.startsWith("@/")
          ? resolve(root, name.slice(2))
          : resolve(dirname(file), name);
        const target = [
          base,
          `${base}.ts`,
          `${base}.tsx`,
          resolve(base, "index.ts"),
        ].find(
          (p) =>
            existsSync(p) && (extname(p) === ".ts" || extname(p) === ".tsx"),
        );
        if (target) {
          const other = relative(root, target).split("/")[0];
          if (target.startsWith(root) && other !== owner) {
            if (!allowed[owner]?.includes(other))
              errors.push(`${file}: forbidden dependency on ${other}`);
            if (!name.startsWith("@/") || !target.endsWith("/index.ts"))
              errors.push(
                `${file}: import ${other} through its public @/${other} entry`,
              );
          }
          edges.push(target);
        }
      }
    }
    ts.forEachChild(node, inspect);
  }
  inspect(source);
  graph.set(file, edges);
}
const visited = new Set();
function checkCycles(file, stack = []) {
  if (stack.includes(file)) {
    errors.push(
      `Import cycle: ${[...stack, file].map((p) => relative(root, p)).join(" → ")}`,
    );
    return;
  }
  if (visited.has(file)) return;
  for (const dependency of graph.get(file) ?? [])
    checkCycles(dependency, [...stack, file]);
  visited.add(file);
}
for (const file of files) checkCycles(file);
if (errors.length) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
} else
  console.log(
    `Module boundaries and acyclic imports verified (${files.length} files).`,
  );
