/** Every source file under src/ has its mirrored test (FRONTEND-TEST-STRUCTURE, rule 53). */

import { missingMirroredTests, sourceFiles } from "@commentary-sync/client/structure";
import { join } from "path";

const ROOT = join(__dirname, "..");

test("there is source to check", () => {
  expect(sourceFiles(join(ROOT, "src")).length).toBeGreaterThan(0);
});

test("every source file has a mirrored test", () => {
  expect(missingMirroredTests(ROOT)).toEqual([]);
});
