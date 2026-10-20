import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

import { missingMirroredTests, sourceFiles } from "../src/structure.ts";

function app(files: string[]): string {
  const root = mkdtempSync(join(tmpdir(), "structure-"));
  for (const file of files) {
    mkdirSync(dirname(join(root, file)), { recursive: true });
    writeFileSync(join(root, file), "");
  }
  return root;
}

test("a source file with its mirrored test passes, in .ts or .tsx", () => {
  const root = app(["src/lib/api.ts", "__tests__/lib/test_api.test.ts", "src/App.tsx", "__tests__/test_App.test.tsx"]);
  assert.deepEqual(missingMirroredTests(root), []);
});

test("a source file without one is reported, by path", () => {
  const root = app(["src/hooks/useLoad.ts", "__tests__/test_useLoad.test.ts"]);
  assert.deepEqual(missingMirroredTests(root), ["src/hooks/useLoad.ts"]);
});

test("type declarations and other files aren't source", () => {
  const root = app(["src/env.d.ts", "src/logo.png", "src/deep/er/x.ts"]);
  assert.deepEqual(
    sourceFiles(join(root, "src")).map((file) => file.slice(root.length + 1)),
    ["src/deep/er/x.ts"],
  );
});
