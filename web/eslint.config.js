import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "dist-demo",
      "coverage",
      "playwright-report",
      "test-results",
      "src/api/schema.d.ts",
    ],
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.strict],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Handbook section 2: all data goes through the generated client, never raw fetch.
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Use the generated client in src/lib/api.ts." },
      ],
      "no-console": "error",
    },
  },
  {
    files: ["src/lib/api.ts", "tests/**"],
    rules: { "no-restricted-globals": "off" },
  },
);
