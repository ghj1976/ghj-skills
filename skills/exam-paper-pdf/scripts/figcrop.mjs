#!/usr/bin/env node
/**
 * 试卷插图裁剪 / 体检 / 拼版。
 *
 * 依赖: npm i @napi-rs/canvas   （单个包，自带预编译二进制，无需 node-gyp）
 *
 * 子命令:
 *
 * 1) 自动量边界（先用它，别靠肉眼估）
 *    node figcrop.mjs auto img/p01.jpg 780 1600 1150 1800 --pad 10
 *    → 在窗口 (x0,y0)-(x1,y1) 内按像素墨迹求包围盒，输出建议 box=(x,y,w,h)
 *    窗口要只框住这张图；窗口四边若"贴边"，说明图被窗口截断或窗口混入了邻行文字，
 *    换窗口重量，直到四边都不贴。
 *
 * 2) 批量裁剪
 *    node figcrop.mjs crop spec.json -o figs
 *    spec.json: {"figs":[{"name":"q2","page":"img/p01.jpg","box":[772,1618,142,128]}]}
 *    box 也可以写 "auto" + "window":[x0,y0,x1,y1]，由程序自动量。
 *
 * 3) 体检（出 PDF 前必做）
 *    node figcrop.mjs check figs --min 3
 *    逐张报告墨迹到四边的距离；任何一边 < min 就报警（多半被切了）。
 *    注意：若裁剪框内混进了邻近的文字行，也会报"贴边"，此时要收窗口而不是扩边。
 *
 * 4) 拼版目检（一屏看完所有图）
 *    node figcrop.mjs sheet figs out.png --width 720
 */
import fs from 'fs';
import path from 'path';
import { createCanvas, loadImage } from '@napi-rs/canvas';

const DARK = 150; // 灰度阈值：低于它算墨迹

function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('-') && a.length === 2) {          // 短选项 -o / -w
      const k = a.slice(1);
      const v = argv[i + 1] && !argv[i + 1].startsWith('-') ? argv[++i] : true;
      out[k] = v;
    } else if (a.startsWith('--')) {
      const k = a.slice(2);
      const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
      out[k] = v;
    } else out._.push(a);
  }
  return out;
}

async function imageData(file) {
  const img = await loadImage(file);
  const cv = createCanvas(img.width, img.height);
  const ctx = cv.getContext('2d');
  ctx.drawImage(img, 0, 0);
  return { w: img.width, h: img.height, data: ctx.getImageData(0, 0, img.width, img.height).data, img };
}

function inkBBox({ w, h, data }, x0, y0, x1, y1) {
  let minX = 1e9, minY = 1e9, maxX = -1, maxY = -1;
  for (let y = Math.max(0, y0); y < Math.min(h, y1); y++) {
    for (let x = Math.max(0, x0); x < Math.min(w, x1); x++) {
      const i = (y * w + x) * 4;
      if ((data[i] + data[i + 1] + data[i + 2]) / 3 < DARK) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  return maxX < 0 ? null : { minX, minY, maxX, maxY };
}

async function cmdAuto(a) {
  const [file, x0, y0, x1, y1] = a._.slice(1);
  const pad = Number(a.pad ?? 10);
  const im = await imageData(file);
  const bb = inkBBox(im, +x0, +y0, +x1, +y1);
  if (!bb) return console.log('窗口内没有墨迹');
  const touch = [];
  if (bb.minX <= +x0 + 1) touch.push('左');
  if (bb.maxX >= +x1 - 2) touch.push('右');
  if (bb.minY <= +y0 + 1) touch.push('上');
  if (bb.maxY >= +y1 - 2) touch.push('下');
  console.log(`墨迹=(${bb.minX},${bb.minY})-(${bb.maxX},${bb.maxY})`);
  console.log(`box=(${Math.max(0, bb.minX - pad)},${Math.max(0, bb.minY - pad)},` +
              `${bb.maxX - bb.minX + 1 + 2 * pad},${bb.maxY - bb.minY + 1 + 2 * pad})`);
  if (touch.length) console.log(`⚠ 贴边: ${touch.join('/')} —— 图可能被窗口截断，或窗口混入了邻行文字`);
}

async function cmdCrop(a) {
  const spec = JSON.parse(fs.readFileSync(a._[1], 'utf8'));
  const outdir = a.o || a.out || 'figs';
  fs.mkdirSync(outdir, { recursive: true });
  const cache = new Map();
  for (const fig of spec.figs) {
    const page = fig.page;
    if (!cache.has(page)) cache.set(page, await loadImage(page));
    const img = cache.get(page);
    const cv0 = createCanvas(img.width, img.height);
    const c0 = cv0.getContext('2d');
    c0.drawImage(img, 0, 0);
    let box = fig.box;
    if (box === 'auto') {
      const [x0, y0, x1, y1] = fig.window;
      const bb = inkBBox({ w: img.width, h: img.height, data: c0.getImageData(0, 0, img.width, img.height).data }, x0, y0, x1, y1);
      if (!bb) { console.log(`  ! ${fig.name} 窗口无墨迹`); continue; }
      const pad = fig.pad ?? 10;
      box = [Math.max(0, bb.minX - pad), Math.max(0, bb.minY - pad), bb.maxX - bb.minX + 1 + 2 * pad, bb.maxY - bb.minY + 1 + 2 * pad];
    }
    const [x, y, w, h] = box;
    const out = createCanvas(w, h);
    out.getContext('2d').drawImage(cv0, x, y, w, h, 0, 0, w, h);
    const file = path.join(outdir, fig.name + '.png');
    fs.writeFileSync(file, await out.encode('png'));
    console.log(`${fig.name.padEnd(16)} ${w}x${h}  from ${path.basename(page)} (${x},${y})`);
  }
}

async function cmdCheck(a) {
  const dir = a._[1];
  const min = Number(a.min ?? 3);
  let bad = 0;
  for (const f of fs.readdirSync(dir).filter((f) => f.endsWith('.png')).sort()) {
    const im = await imageData(path.join(dir, f));
    const bb = inkBBox(im, 0, 0, im.w, im.h);
    if (!bb) { console.log(`${f} 空白图`); continue; }
    const m = { 左: bb.minX, 右: im.w - 1 - bb.maxX, 上: bb.minY, 下: im.h - 1 - bb.maxY };
    const tight = Object.entries(m).filter(([, v]) => v < min).map(([k]) => k);
    if (tight.length) bad++;
    console.log(`${f.padEnd(22)} ${String(im.w).padStart(4)}x${String(im.h).padEnd(4)}  ` +
      `边距 左${m.左} 右${m.右} 上${m.上} 下${m.下}` + (tight.length ? `  ⚠ 过紧:${tight.join('')}` : ''));
  }
  if (bad) {
    console.log(`\n${bad} 张贴边。贴边不一定是切图，也可能是框里混进了邻行文字——先看拼版目检图再决定。`);
    process.exitCode = 1;
  }
}

async function cmdSheet(a) {
  const [dir, outFile] = a._.slice(1);
  const width = Number(a.width ?? 720);
  const names = a._.slice(3);
  const files = names.length
    ? names.map((n) => (n.endsWith('.png') ? path.join(dir, n) : path.join(dir, n + '.png')))
    : fs.readdirSync(dir).filter((f) => f.endsWith('.png')).sort().map((f) => path.join(dir, f));
  const items = [];
  for (const f of files) items.push([path.basename(f, '.png'), await loadImage(f)]);
  const labelH = 30, gap = 24;
  const heights = items.map(([, im]) => Math.max(40, Math.round(im.height * width / im.width)));
  const totalH = heights.reduce((s, h) => s + h + labelH + gap, 20);
  const cv = createCanvas(width + 40, totalH);
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, cv.width, cv.height);
  let y = 10;
  items.forEach(([name, im], i) => {
    ctx.fillStyle = '#c00';
    ctx.font = 'bold 20px sans-serif';
    ctx.fillText(name, 20, y + 20);
    y += labelH;
    ctx.drawImage(im, 20, y, width, heights[i]);
    ctx.strokeStyle = '#bbb';
    ctx.strokeRect(20, y, width, heights[i]);
    y += heights[i] + gap;
  });
  fs.writeFileSync(outFile, await cv.encode('png'));
  console.log(outFile, cv.width + 'x' + cv.height);
}

const a = parseArgs(process.argv.slice(2));
const cmd = a._[0];
if (cmd === 'auto') await cmdAuto(a);
else if (cmd === 'crop') await cmdCrop(a);
else if (cmd === 'check') await cmdCheck(a);
else if (cmd === 'sheet') await cmdSheet(a);
else console.log(fs.readFileSync(new URL(import.meta.url)).toString().split('*/')[0]);
