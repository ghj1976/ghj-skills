#!/usr/bin/env node
/**
 * PDF 逐页渲染成 PNG，用来"看"最终成品（校验分页、图是否被切、有没有压字）。
 *
 * 依赖: npm i pdfjs-dist @napi-rs/canvas
 *
 * 用法:
 *   node render_pages.mjs out/答案_A4.pdf work/pages
 *   node render_pages.mjs out/答案_A4.pdf work/pages --scale 1.6 --pages 1,5,11
 *
 * 说明:
 *   机器上通常没有 pdftoppm；pdfjs + skia canvas 是纯 npm 方案，跨平台且不需要编译。
 *   渲染出来逐页看，比只看 HTML 预览可靠——分页是打印时才发生的。
 */
import fs from 'fs';
import path from 'path';
import { createCanvas } from '@napi-rs/canvas';

const args = process.argv.slice(2);
const [pdfPath, outDir] = args;
if (!pdfPath || !outDir) {
  console.error('用法: node render_pages.mjs <pdf> <outdir> [--scale 1.6] [--pages 1,2,3]');
  process.exit(1);
}
const opt = {};
for (let i = 2; i < args.length; i++) {
  if (args[i].startsWith('--')) opt[args[i].slice(2)] = args[i + 1] && !args[i + 1].startsWith('--') ? args[++i] : true;
}
const scale = Number(opt.scale ?? 1.6);
const only = opt.pages ? String(opt.pages).split(',').map(Number) : null;

const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
const data = new Uint8Array(fs.readFileSync(pdfPath));
const doc = await pdfjs.getDocument({ data, useSystemFonts: false }).promise;
fs.mkdirSync(outDir, { recursive: true });
console.log('pages', doc.numPages);
for (let p = 1; p <= doc.numPages; p++) {
  if (only && !only.includes(p)) continue;
  const page = await doc.getPage(p);
  const vp = page.getViewport({ scale });
  const canvas = createCanvas(Math.ceil(vp.width), Math.ceil(vp.height));
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, vp.width, vp.height);
  await page.render({ canvasContext: ctx, viewport: vp }).promise;
  const out = path.join(outDir, `page${String(p).padStart(2, '0')}.png`);
  fs.writeFileSync(out, await canvas.encode('png'));
  console.log(out, `${Math.ceil(vp.width)}x${Math.ceil(vp.height)}`);
}
