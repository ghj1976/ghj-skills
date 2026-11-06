#!/usr/bin/env node
/**
 * Markdown → 单文件 HTML（打印版 A4 / 屏幕版）。
 *
 * 为什么不用 pandoc: 目标机器常常没有 pandoc / libreoffice，而 Node 基本都有。
 * 这个转换器只支持写试卷解析需要的子集，够用且行为可预期。
 *
 * 用法:
 *   node md2page.mjs 答案.md 答案.html print    # A4 打印版（交给 makepdf.mjs 出 PDF）
 *   node md2page.mjs 答案.md 答案.html screen   # 网页版（给人看 / 另存 PDF）
 *
 * 支持的语法:
 *   # ~ ###### 标题
 *   段落、**加粗**、`代码`、---（分隔线）
 *   - 列表（含两格缩进的续行）
 *   | 表格 |
 *   > 引用块 → 渲染成"题目框"（浅底 + 左侧色条），用来装原题
 *   ![说明](figs/x.png) → <figure> + <figcaption>
 *
 * 图片路径会按"输出 HTML 所在目录"重算，因此 md 和 html 可以不在同一层。
 */
import fs from 'fs';
import path from 'path';

const [inMd, outHtml, modeArg] = process.argv.slice(2);
if (!inMd || !outHtml) {
  console.error('用法: node md2page.mjs in.md out.html [print|screen]');
  process.exit(1);
}
const mode = modeArg === 'screen' ? 'screen' : 'print';
const mdDir = path.dirname(path.resolve(inMd));
const outDir = path.dirname(path.resolve(outHtml));

const md = fs.readFileSync(inMd, 'utf8');
const lines = md.split(/\r?\n/);

function imgSrc(src) {
  if (/^(https?:|file:|data:)/.test(src)) return src;
  const abs = path.resolve(mdDir, src);
  let rel = path.relative(outDir, abs).split(path.sep).join('/');
  return rel.startsWith('.') ? rel : './' + rel;
}

const inline = (s) => s
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, src) => `<img src="${imgSrc(src)}" alt="${alt}">`)
  .replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>')   // 必须容忍跨行：**…** 里常有手动换行
  .replace(/`([^`]+?)`/g, '<code>$1</code>');

const out = [];
let i = 0;
while (i < lines.length) {
  const l = lines[i];
  if (/^\s*$/.test(l)) { i++; continue; }
  if (/^---+\s*$/.test(l)) { out.push('<hr>'); i++; continue; }

  let m;
  if ((m = l.match(/^(#{1,6})\s+(.*)$/))) {
    out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`);
    i++; continue;
  }
  // 独占一行的图片 → figure（带图注）
  if ((m = l.match(/^!\[([^\]]*)\]\(([^)]+)\)\s*$/))) {
    out.push(`<figure><img src="${imgSrc(m[2])}" alt="${m[1]}"><figcaption>${m[1]}</figcaption></figure>`);
    i++; continue;
  }
  if (/^\|/.test(l)) {
    const rows = [];
    while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
    let html = '<table>';
    rows.forEach((r, idx) => {
      const cells = r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
      if (idx === 1 && cells.every((c) => /^:?-{2,}:?$/.test(c))) return; // 分隔行
      const tag = idx === 0 ? 'th' : 'td';
      html += '<tr>' + cells.map((c) => `<${tag}>${inline(c)}</${tag}>`).join('') + '</tr>';
    });
    out.push(html + '</table>');
    continue;
  }
  if (/^>\s?/.test(l)) {
    const buf = [];
    while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ''));
    out.push('<div class="q">' + buf.map(inline).join('<br>') + '</div>');
    continue;
  }
  if (/^[-*]\s+/.test(l)) {
    const buf = [];
    while (i < lines.length && lines[i].trim() !== '' && /^([-*]\s+|\s{2,})/.test(lines[i])) {
      if (/^[-*]\s+/.test(lines[i])) buf.push(lines[i++].replace(/^[-*]\s+/, ''));
      else buf[buf.length - 1] += ' ' + lines[i++].trim();
    }
    out.push('<ul>' + buf.map((b) => `<li>${inline(b)}</li>`).join('') + '</ul>');
    continue;
  }
  // 普通段落：连着的行用 <br> 连接（试卷里一行一个选项）
  const buf = [];
  while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^#{1,6}\s/.test(lines[i]) &&
         !/^\|/.test(lines[i]) && !/^>/.test(lines[i]) && !/^[-*]\s+/.test(lines[i]) &&
         !/^!\[/.test(lines[i])) {
    buf.push(lines[i++]);
  }
  out.push('<p>' + buf.map(inline).join('<br>') + '</p>');
}

const printCSS = `
@page { size: A4; margin: 14mm 13mm 15mm 13mm; }
html,body{margin:0;padding:0;}
body{font-family:"Microsoft YaHei","PingFang SC","Source Han Sans SC",sans-serif;font-size:10.2pt;line-height:1.56;color:#111;}
h1{font-size:16.5pt;text-align:center;margin:0 0 2mm;font-weight:700;}
h2{font-size:13pt;text-align:center;margin:0 0 3mm;font-weight:600;color:#222;break-after:avoid;page-break-after:avoid;}
h3{font-size:11.8pt;margin:4mm 0 1.3mm;padding-left:2.5mm;border-left:1.2mm solid #2b6cb0;color:#123;break-after:avoid;page-break-after:avoid;}
p{margin:1mm 0;}
table{border-collapse:collapse;width:100%;margin:2mm 0;font-size:9.6pt;break-inside:avoid;page-break-inside:avoid;}
th,td{border:0.3mm solid #999;padding:1.2mm 1.8mm;text-align:left;vertical-align:top;}
th{background:#eef3f9;}
.q{margin:1.2mm 0 1.8mm;padding:1.8mm 3mm;background:#f7f9fb;border:0.25mm solid #d6dee6;border-left:1.2mm solid #6f97c4;font-size:10pt;}
figure{margin:2mm 0 2.5mm;text-align:center;break-inside:avoid;page-break-inside:avoid;}
figure img{max-width:100%;max-height:67mm;border:0.2mm solid #ccc;}
figcaption{font-size:8.5pt;color:#666;margin-top:1mm;}
hr{border:none;border-top:0.3mm solid #ccc;margin:4mm 0;}
ul{margin:1.2mm 0 1.2mm 5mm;padding:0;}
li{margin:0.5mm 0;break-inside:avoid;page-break-inside:avoid;}
strong{color:#a11;font-weight:700;}
code{background:#f2f2f2;padding:0 1mm;border-radius:1mm;}
`;

const screenCSS = `
body{max-width:920px;margin:0 auto;padding:32px 26px 90px;font-family:"Microsoft YaHei","PingFang SC",sans-serif;line-height:1.85;color:#1a1a1a;font-size:16px;background:#fff;}
h1{font-size:25px;text-align:center;margin:6px 0;}
h2{font-size:20px;text-align:center;margin:0 0 22px;font-weight:600;color:#333;}
h3{font-size:18px;margin:30px 0 10px;padding-left:10px;border-left:4px solid #2b6cb0;color:#1a365d;}
p{margin:8px 0;}
table{border-collapse:collapse;margin:12px 0;width:100%;font-size:15px;}
th,td{border:1px solid #bbb;padding:6px 10px;text-align:left;vertical-align:top;}
th{background:#eef3f9;}
.q{margin:10px 0 12px;padding:10px 14px;background:#f7f9fb;border:1px solid #dce4ec;border-left:5px solid #6f97c4;border-radius:3px;}
figure{margin:14px 0;text-align:center;}
figure img{max-width:100%;border:1px solid #ddd;}
figcaption{font-size:13px;color:#777;margin-top:6px;}
hr{border:none;border-top:1px solid #ddd;margin:26px 0;}
ul{margin:8px 0 8px 22px;}
strong{color:#b02a37;}
code{background:#f3f3f3;padding:1px 4px;border-radius:3px;}
@media print{body{max-width:none;padding:0;font-size:13px;}}
`;

const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>${path.basename(inMd, path.extname(inMd))}</title>
<style>${mode === 'print' ? printCSS : screenCSS}</style></head><body>
${out.join('\n')}
</body></html>`;

fs.writeFileSync(outHtml, html, 'utf8');
console.log('written', outHtml, html.length, mode);
