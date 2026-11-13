// 디자인 시스템 검사: tokens.css 밖에서 원시 값(색상, px, 시간, 이징, 서체 등)을 쓰면 실패한다.
// 실행: npm run lint:design (npm run lint에 포함). 외부 패키지 없이 Node 기본 기능만 쓴다.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const SRC = join(ROOT, 'src');
const TOKENS_FILE = join(SRC, 'styles', 'tokens.css');

const NUMBER = String.raw`(?:\d+\.?\d*|\.\d+)`;
const LENGTH_UNITS = 'px|rem|em|vw|vh|svh|dvh|lvh|ch|pt|vmin|vmax|cqi|cqw|cqh|cqb|cqmin|cqmax';
const ALLOWED_VIEWPORT = /^100(?:dvh|svh|vh|vw)$/;
const NAMED_COLORS = 'white|black|red|green|blue|gray|grey|yellow|orange|purple|pink|brown';

// 속성 값이 var(...)나 허용 키워드로 시작하지 않으면 위반인 규칙
const PROPERTY_RULES = [
  [
    'font-family',
    /(?<![\w-])font-family\s*:\s*(?!\s|var\(|inherit\b)/,
    'font-family는 var(--font-*)만 쓴다',
  ],
  [
    'font-size',
    /(?<![\w-])font-size\s*:\s*(?!\s|var\(|inherit\b)/,
    'font-size는 var(--text-*)만 쓴다',
  ],
  [
    'font-weight',
    /(?<![\w-])font-weight\s*:\s*(?!\s|var\(|inherit\b)/,
    'font-weight는 var(--weight-*)만 쓴다',
  ],
  [
    'line-height',
    /(?<![\w-])line-height\s*:\s*(?!\s|var\(|inherit\b|normal\b)/,
    'line-height는 var(--leading-*)만 쓴다',
  ],
  [
    'letter-spacing',
    /(?<![\w-])letter-spacing\s*:\s*(?!\s|var\(|inherit\b|normal\b)/,
    'letter-spacing은 var(--tracking-*)만 쓴다',
  ],
  ['z-index', /(?<![\w-])z-index\s*:\s*(?!\s|var\(|auto\b)/, 'z-index는 var(--z-*)만 쓴다'],
  [
    'opacity',
    /(?<![\w-])opacity\s*:\s*(?!\s|var\(|0(?![\d.])|1(?![\d.])|inherit\b)/,
    'opacity는 var(--opacity-*)나 0, 1만 쓴다',
  ],
  [
    'border-radius',
    /(?<![\w-])border(?:-[a-z]+)*-radius\s*:\s*(?!\s|var\(|0(?![\d.])|inherit\b)/,
    '모서리는 var(--radius-*)만 쓴다',
  ],
  [
    'box-shadow',
    /(?<![\w-])box-shadow\s*:\s*(?!\s|var\(|none\b|inherit\b)/,
    '그림자는 var(--shadow-*)만 쓴다',
  ],
];

const violations = [];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

// 주석은 같은 줄 수를 유지한 채 공백으로 바꿔서 줄 번호가 어긋나지 않게 한다
function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
}

function report(file, lineNo, message, snippet) {
  violations.push(`${relative(ROOT, file)}:${lineNo}  ${message}  ->  ${snippet.trim()}`);
}

const files = walk(SRC);
const cssFiles = files.filter((f) => f.endsWith('.css'));
const scriptFiles = files.filter((f) => /\.(jsx?|mjs)$/.test(f));

// 1) tokens.css 에 정의된 토큰 이름
const tokensText = stripComments(readFileSync(TOKENS_FILE, 'utf8'));
const defined = new Set([...tokensText.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));

// 2) CSS 검사 (tokens.css 제외)
let tokenReferences = 0;
for (const file of cssFiles) {
  if (file === TOKENS_FILE) continue;
  const lines = stripComments(readFileSync(file, 'utf8')).split('\n');
  const localDefs = new Set([...lines.join('\n').matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
  lines.forEach((line, index) => {
    const lineNo = index + 1;
    const isMediaCondition = /^\s*@(media|container)\b/.test(line);

    if (/#[0-9a-fA-F]{3,8}\b/.test(line)) report(file, lineNo, '헥스 색상 금지', line);
    if (/\b(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color-mix)\s*\(/i.test(line)) {
      report(file, lineNo, '색상 함수 금지(tokens.css에서 정의)', line);
    }
    if (new RegExp(String.raw`:\s*[^;]*\b(?:${NAMED_COLORS})\b`, 'i').test(line)) {
      report(file, lineNo, '색상 이름 금지', line);
    }
    if (/\b(?:cubic-bezier|steps|linear)\s*\(/.test(line)) {
      report(file, lineNo, '이징 직접 지정 금지(var(--ease*))', line);
    }
    if (new RegExp(String.raw`(?<![\w.-])${NUMBER}(?:ms|s)\b`).test(line)) {
      report(file, lineNo, '시간 직접 지정 금지(var(--duration-*))', line);
    }
    if (!isMediaCondition) {
      const lengthPattern = new RegExp(
        String.raw`(?<![\w.-])-?${NUMBER}(?:${LENGTH_UNITS})\b`,
        'g',
      );
      for (const match of line.matchAll(lengthPattern)) {
        if (!ALLOWED_VIEWPORT.test(match[0])) {
          report(file, lineNo, `길이 직접 지정 금지(${match[0]})`, line);
        }
      }
    }
    for (const [, pattern, message] of PROPERTY_RULES) {
      if (pattern.test(line)) report(file, lineNo, message, line);
    }
    for (const match of line.matchAll(/var\(\s*(--[\w-]+)/g)) {
      tokenReferences += 1;
      if (!defined.has(match[1]) && !localDefs.has(match[1])) {
        report(file, lineNo, `정의되지 않은 토큰 ${match[1]}`, line);
      }
    }
  });
}

// 3) JSX/JS 검사: 인라인 스타일과 원시 색상 금지
for (const file of scriptFiles) {
  const lines = readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, index) => {
    const lineNo = index + 1;
    if (/\bstyle\s*=\s*\{/.test(line))
      report(file, lineNo, '인라인 style 금지(className과 토큰 사용)', line);
    if (/['"`]#[0-9a-fA-F]{3,8}['"`]/.test(line)) report(file, lineNo, '헥스 색상 금지', line);
    if (/\b(?:rgb|rgba|hsl|hsla)\s*\(/i.test(line)) report(file, lineNo, '색상 함수 금지', line);
  });
}

if (violations.length > 0) {
  console.error(
    `디자인 시스템 위반 ${violations.length}건 (원시 값은 src/styles/tokens.css 에만 쓴다)\n`,
  );
  for (const v of violations) console.error(`  ${v}`);
  process.exit(1);
}

console.log(
  `디자인 시스템 검사 통과: CSS ${cssFiles.length - 1}개, 스크립트 ${scriptFiles.length}개, 토큰 참조 ${tokenReferences}건, 정의된 토큰 ${defined.size}개`,
);
