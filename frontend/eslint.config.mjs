import tsParser from '@typescript-eslint/parser'

export default [
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts', 'public/**'] },
  {
    files: ['**/*.{ts,tsx,js,jsx,mjs,cjs}'],
    languageOptions: { parser: tsParser, parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } } },
    rules: {
      'constructor-super': 'error',
      'no-constant-condition': ['error', { checkLoops: false }],
      'no-dupe-args': 'error',
      'no-dupe-keys': 'error',
      'no-duplicate-case': 'error',
      'no-func-assign': 'error',
      'no-unreachable': 'error',
      'no-unsafe-finally': 'error',
      'valid-typeof': 'error',
    },
  },
]
