#!/usr/bin/env node
/**
 * HTML → A4 PDF（带页脚页码），通过 Chrome DevTools Protocol 打印。
 *
 * 依赖: npm i puppeteer-core   （不下载 Chromium，连本机已有的 Chrome）
 *
 * 为什么不用 `chrome --headless --print-to-pdf`:
 *   - 命令行无法设置页眉页脚模板 → 拿不到"第 x 页 / 共 y 页"；
 *   - 用 CSS position:fixed 假装页脚，在 CDP 打印里会叠到正文上（实测压在页面顶部正文上）。
 *   CDP 的 page.pdf({displayHeaderFooter, footerTemplate}) 才是正路。
 *
 * 用法:
 *   # 先起一个带调试端口的 Chrome（Windows 版 WSL 路径见下）
 *   "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
 *     --headless=new --disable-gpu --remote-debugging-port=9333 \
 *     --user-data-dir="C:\\Temp\\chrome-cdp" about:blank &
 *
 *   node makepdf.mjs work/print.html out/答案_A4.pdf
 *   node makepdf.mjs work/print.html out/答案_A4.pdf --footer "2026 朝阳高三期中化学 · 参考答案与解析"
 *
 * 注意: 输出路径请写 WSL 路径（/mnt/d/...）。写成 Windows 路径（D:\\...）会被当成本地文件名，
 *       生成一个名字里带冒号和反斜杠的文件。
 */
import fs from 'fs';
import path from 'path';
import puppeteer from 'puppeteer-core';

const args = process.argv.slice(2);
const [htmlPath, outPdf] = args;
if (!htmlPath || !outPdf) {
  console.error('用法: node makepdf.mjs <html> <out.pdf> [--footer 文本] [--browser http://127.0.0.1:9333]');
  process.exit(1);
}
const opt = {};
for (let i = 2; i < args.length; i++) {
  if (args[i].startsWith('--')) opt[args[i].slice(2)] = args[i + 1] && !args[i + 1].startsWith('--') ? args[++i] : true;
}

const browserURL = opt.browser || 'http://127.0.0.1:9333';
const footerText = opt.footer || '';

const abs = path.resolve(htmlPath);
if (!fs.existsSync(abs)) { console.error('找不到 HTML:', abs); process.exit(1); }

// 浏览器在 Windows 上跑时，/mnt/d/... 这种 WSL 路径它打不开，要换成 file:///D:/...
function toFileUrl(p, win) {
  if (win) {
    const m = p.match(/^\/mnt\/([a-zA-Z])\/(.*)$/);
    if (m) return `file:///${m[1].toUpperCase()}:/${m[2]}`;
  }
  return 'file://' + p.split(path.sep).join('/');
}

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const footerTemplate = `
<div style="width:100%;font-size:8px;color:#777;text-align:center;font-family:'Microsoft YaHei',sans-serif;">
  第 <span class="pageNumber"></span> 页 / 共 <span class="totalPages"></span> 页${footerText ? '　·　' + esc(footerText) : ''}
</div>`;

const browser = await puppeteer.connect({ browserURL, defaultViewport: null });
const page = await browser.newPage();

// 浏览器可能跑在 WSL（认 /mnt/...），也可能跑在 Windows（只认 D:\...）。
// 不猜，先按原生路径开，失败再换成 Windows 映射。
const nativeUrl = toFileUrl(abs, false);
const winUrl = toFileUrl(abs, true);
let fileUrl = nativeUrl;
try {
  await page.goto(nativeUrl, { waitUntil: 'networkidle0' });
} catch (e) {
  if (winUrl !== nativeUrl) {
    fileUrl = winUrl;
    await page.goto(winUrl, { waitUntil: 'networkidle0' });
  } else throw e;
}
await page.emulateMediaType('print');
await page.pdf({
  path: path.resolve(outPdf),
  format: 'A4',
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: '<div></div>',
  footerTemplate,
  margin: { top: '14mm', bottom: '16mm', left: '13mm', right: '13mm' },
});
await page.close();
await browser.disconnect();
console.log('pdf →', path.resolve(outPdf), `(${fileUrl})`);
