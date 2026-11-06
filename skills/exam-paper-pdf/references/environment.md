# 环境与依赖

## 典型环境

- Windows 11 + WSL2（Ubuntu），工作目录在 `/mnt/d/...` 或 `/mnt/e/...`
- Node 在 WSL 里（v24），npm 可用
- Chrome 装在 Windows 侧：`/mnt/c/Program Files/Google/Chrome/Application/chrome.exe`
- 没有：pandoc、libreoffice、pdftoppm/poppler、python3-pip、PIL、ImageMagick、中文字体

## 一次性准备

```bash
mkdir -p work && cd work
npm init -y >/dev/null
npm i @napi-rs/canvas pdfjs-dist puppeteer-core
```

- `@napi-rs/canvas`：读 JPEG/PNG、裁切、拼版、渲染 PDF 页；预编译二进制，不需要 node-gyp。
- `pdfjs-dist`：解析 PDF 页面（`legacy/build/pdf.mjs`，Node 里 import 必须用 legacy 版）。
- `puppeteer-core`：只连本机 Chrome，不下载 Chromium（比 `puppeteer` 小一个量级）。

可选：`jpeg-js`、`pngjs`（纯 JS 解码，不依赖 skia，慢但兼容性好）。

## 启动 / 关闭 Chrome 调试实例

```bash
# 启动（Windows 版 Chrome，端口在 Windows 上监听，WSL 里 127.0.0.1 可达）
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu --no-first-run \
  --user-data-dir="C:\\Temp\\chrome-cdp" \
  --remote-debugging-port=9333 about:blank &

# 确认端口通
curl -s http://127.0.0.1:9333/json/version | head -3

# 用完关掉（否则一直挂着）
node -e "import('puppeteer-core').then(async({default:p})=>{const b=await p.connect({browserURL:'http://127.0.0.1:9333'});await b.close()})"
```

若 `curl` 不通：Chrome 可能因为已有实例在用同一个 `user-data-dir` 而没开新端口，
换一个目录（`chrome-cdp2`）再起。

## 纯命令行打印（不需要页码时更快）

```bash
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --headless=new --disable-gpu --no-pdf-header-footer \
  --user-data-dir="C:\\Temp\\chrome-pdf" \
  --print-to-pdf="/mnt/d/test/yy/out.pdf" \
  "file:///D:/test/yy/work/print.html"
```

注意两边都要写对：`--print-to-pdf` 给的是 **Windows 路径**（因为进程是 Windows 的），
HTML 用 `file:///D:/...` 形式。而 **Node 脚本里**给的都是 **WSL 路径**（`/mnt/d/...`）。

## 路径速查

| 场景 | 写法 |
|---|---|
| Node 脚本参数（输入/输出） | `/mnt/d/test/yy/out.pdf` |
| Chrome 命令行 `--print-to-pdf` | `D:\test\yy\out.pdf` 或 `D:/test/yy/out.pdf` |
| Chrome 要打开的本地 HTML | `file:///D:/test/yy/work/print.html` |
| CDP `page.pdf({path})`（在 Node 里） | `/mnt/d/test/yy/out.pdf` |

## 中文字体

- WSL 里没有中文字体，**不要**在 WSL 里用无头浏览器打印（会变方框）。
- Windows Chrome 自带微软雅黑，`font-family:"Microsoft YaHei"` 即可；
  生成的 PDF 字体会以 `BAAAAA+MicrosoftYaHei` 形式子集嵌入，换机器打印不缺字。

## 常见依赖缺失的替代

| 缺 | 症状 | 替代 |
|---|---|---|
| pandoc | md→docx/pdf 不行 | `md2page.mjs` + Chrome 打印 |
| pdftoppm | 无法把 PDF 转图 | `render_pages.mjs`（pdfjs + canvas） |
| pdftotext | 抽不到文字 | 图片型 PDF 本来就没文字层，走读图 |
| PIL / ImageMagick | 不能裁图 | `figcrop.mjs`（canvas） |
| pip | 装不了 python 包 | 用 npm 生态替代 |
