/** FRONTEND-TEST-STRUCTURE and rule 53, for any app in this repo: every
 * source file under `src/` has a test at the same path under `__tests__/`,
 * named test_<file>.test.ts(x). The frontend twin of tests/test_structure.py.
 *
 *   expect(missingMirroredTests(appRoot)).toEqual([]);
 */

import { existsSync, readdirSync, statSync } from "node:fs";
import { join, parse, relative } from "node:path";

const SOURCE_FILE = /\.(ts|tsx)$/;
const TEST_EXTENSIONS = ["ts", "tsx"];

/** Source files (relative to `root`) whose mirrored test is missing. */
export function missingMirroredTests(root: string): string[] {
  const source = join(root, "src");
  return sourceFiles(source)
    .filter((file) => !mirroredTests(root, relative(source, file)).some((test) => existsSync(test)))
    .map((file) => relative(root, file));
}

/** Every source file under `directory`, at any depth. */
export function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return SOURCE_FILE.test(name) && !name.endsWith(".d.ts") ? [path] : [];
  });
}

function mirroredTests(root: string, file: string): string[] {
  const { dir, name } = parse(file);
  return TEST_EXTENSIONS.map((extension) => join(root, "__tests__", dir, `test_${name}.test.${extension}`));
}
