// eslint-config-expo's flat config, plus the measurable code-quality rules
// as errors, the same as the studio's (web/eslint.config.mjs).
const expoConfig = require("eslint-config-expo/flat");

// eslint-config-expo registers the TypeScript plugin in its own config
// objects; a rule from it needs the plugin in the object that sets the rule.
const typescriptPlugin = expoConfig.find((config) => config.plugins?.["@typescript-eslint"]).plugins[
  "@typescript-eslint"
];

module.exports = [
  ...expoConfig,
  { ignores: ["coverage/**", "node_modules/**", ".expo/**"] },
  {
    plugins: { "@typescript-eslint": typescriptPlugin },
    rules: {
      // Rules 6, 8, 42, 56.
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
    // Tests, tool configs and the style tokens state their values inline.
    files: ["__tests__/**", "*.config.*", "src/theme.ts"],
    rules: { "no-magic-numbers": "off", "max-lines-per-function": "off" },
  },
];
