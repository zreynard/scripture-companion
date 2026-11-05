// QA: the TV page and the sync engine must run on old TV browsers (Chrome 38+, 2014-15).
// 1) their JavaScript must be plain ES5 syntax  2) they must not call newer built-ins without a fallback.
// node tools/qa/es5.js   (needs: npm i acorn)
const fs = require('fs'), acorn = require('acorn');
const R = []; let fails = 0; const T = (n, ok, why) => { if (!ok) fails++; R.push((ok ? 'PASS ' : 'FAIL ') + n + (ok ? '' : '  ' + why)); };
const tv = fs.readFileSync(__dirname + '/../../site_extra/tv/index.html', 'utf8'), live = fs.readFileSync(__dirname + '/../../site_extra/live.js', 'utf8');
const scripts = [...tv.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
for (const [name, code] of [['live.js', live]].concat(scripts.map((c, i) => ['tv page script ' + (i + 1), c]))) {
  try { acorn.parse(code, { ecmaVersion: 5 }); T('E1 ' + name + ' is plain ES5', true); } catch (e) { T('E1 ' + name + ' is plain ES5', false, e.message + ' near: ' + code.slice(Math.max(0, e.pos - 40), e.pos + 40).replace(/\s+/g, ' ')); }
}
// newer built-ins (Chrome version that added them) that the TV code must not rely on
const NEW = [[/\bArray\.from\b/, 45], [/\.includes\(/, 47], [/\bObject\.assign\b/, 45], [/\bObject\.(values|entries)\b/, 54], [/\.padStart\(|\.padEnd\(/, 57], [/\bfetch\(/, 42], [/\.finally\(/, 63], [/\bnew URL\(/, 32], [/\bSymbol\b/, 38], [/\.find(Index)?\(/, 45], [/\.startsWith\(|\.endsWith\(/, 41], [/\.repeat\(/, 41], [/\bMap\(|\bSet\(/, 38], [/\.flat\(|\.flatMap\(/, 69], [/\binset\s*:/, 87], [/\bvar\(--/, 49], [/display\s*:\s*(flex|grid)/, 29], [/\bgap\s*:/, 84], [/aspect-ratio/, 88], [/\bclamp\(/, 79], [/\bnormalize\(/, 34]];
const tvAll = tv.replace(/<script src[^>]*><\/script>/g, '');
for (const [name, code] of [['tv page', tvAll], ['live.js', live]]) {
  const hits = NEW.filter(([re]) => re.test(code)).map(([re, v]) => re.source + ' (Chrome ' + v + ')');
  T('E2 ' + name + ' uses nothing newer than old TV browsers know', hits.length === 0, hits.join(', '));
}
// the newer things live.js does use must each have a guard
T('E3 live.js has its own UTF-8 when TextEncoder is missing', /G\.TextEncoder \?/.test(live) && /G\.TextDecoder \?/.test(live), 'no fallback');
T('E4 BroadcastChannel and Wake Lock are optional', /if \(G\.BroadcastChannel\)/.test(live) && /navigator\.wakeLock && navigator\.wakeLock\.request/.test(tv), 'not guarded');
console.log(R.join('\n')); console.log(`\n${R.length - fails}/${R.length} passed`); process.exit(fails ? 1 : 0);
