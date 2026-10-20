import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const eslintConfig = [
  { ignores: [".next/**", "coverage/**", "node_modules/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Rules 6, 8, 42, 56: the measurable parts, as lint errors.
      "max-depth": ["error", 3],
      "max-lines": ["error", { max: 400, skipBlankLines: true, skipComments: true }],
      "max-lines-per-function": ["error", { max: 50, skipBlankLines: true, skipComments: true }],
      "no-magic-numbers": [
        "error",
        { ignore: [-1, 0, 1, 2], ignoreArrayIndexes: true, ignoreDefaultValues: true, enforceConst: true },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "no-console": "error",
    },
  },
  {
    // Tests and tool configs state their values inline; a named constant for
    // each would hide them.
    files: ["__tests__/**", "*.config.*"],
    rules: { "no-magic-numbers": "off", "max-lines-per-function": "off" },
  },
];

export default eslintConfig;
