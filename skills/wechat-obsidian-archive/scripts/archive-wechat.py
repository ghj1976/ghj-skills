#!/usr/bin/env python3
"""
公众号文章抓取工具
用法: python archive-wechat.py <url> [--output-dir <目录>] [--assets-dir <目录>]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from html_to_markdown import convert, ConversionOptions

WECHAT_UA = (
    "Mozilla/5.0 (Linux; Android 13; V2148A) AppleWebKit/537.36 "
    "Chrome/116.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.49.2600"
)

DEFAULT_OUTPUT_DIR = os.path.expanduser("~/参考资料库/公众号文章")
DEFAULT_ASSETS_DIR_NAME = "assets"


def fetch_page(url: str) -> str:
    result = subprocess.run(
        ["curl.exe", "-s", "-L", "-A", WECHAT_UA, url],
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    return result.stdout


def extract_meta(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    title_el = soup.find(id="activity-name") or soup.find(
        class_="rich_media_title"
    )
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        m = re.search(r'var\s+msg_title\s*=\s*["\']([^"\']+)["\']', html)
        if m:
            title = m.group(1)

    author = ""
    author_el = soup.find(id="js_name") or soup.find(class_="rich_media_meta_nickname")
    if author_el:
        author = author_el.get_text(strip=True)
    if not author:
        m = re.search(r'var\s+msg_nickname\s*=\s*["\']([^"\']+)["\']', html)
        if m:
            author = m.group(1)

    publish_date = ""
    em = soup.find(id="publish_time")
    if em:
        publish_date = em.get_text(strip=True)
    if not publish_date:
        m = re.search(r'var\s+ct\s*=\s*["\']?(\d+)["\']?', html)
        if m:
            ts = int(m.group(1))
            publish_date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    if not publish_date:
        m = re.search(r'"publish_time"\s*:\s*"([^"]+)"', html)
        if m:
            publish_date = m.group(1)
    if not publish_date:
        m = re.search(r'create_time\s*=\s*["\']?(\d+)["\']?', html)
        if m:
            ts = int(m.group(1))
            publish_date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    description = ""
    desc_el = soup.find("meta", attrs={"name": "description"})
    if desc_el and desc_el.get("content"):
        description = desc_el["content"].strip()

    return {
        "title": title or "未知标题",
        "author": author or "未知作者",
        "publish_date": publish_date,
        "description": description,
    }


def extract_content(html: str, assets_dir: str, md_file_path: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find(id="js_content") or soup.find(
        class_="rich_media_content"
    )
    if not content_div:
        return ""

    for tag in content_div.find_all(["script", "style"]):
        tag.decompose()

    md_dir = os.path.dirname(md_file_path) if md_file_path else ""

    for img in content_div.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not src:
            continue
        src = src.replace("&amp;", "&")
        local_path = download_image(src, assets_dir)
        rel_path = os.path.relpath(local_path, md_dir) if md_dir else local_path
        img["src"] = rel_path
        img["alt"] = "图片"
        if "data-src" in img.attrs:
            del img.attrs["data-src"]

    content_html = str(content_div)
    content_html = re.sub(r'<svg[^>]*>.*?</svg>', '', content_html, flags=re.DOTALL)

    options = ConversionOptions(
        heading_style='atx',
        skip_images=False,
        autolinks=True,
    )
    result = convert(content_html, options=options)
    markdown = result.content

    markdown = re.sub(r'&nbsp;', ' ', markdown)
    markdown = re.sub(r'&amp;', '&', markdown)
    markdown = re.sub(r'&lt;', '<', markdown)
    markdown = re.sub(r'&gt;', '>', markdown)
    markdown = re.sub(r'&quot;', '"', markdown)
    markdown = re.sub(r'&#39;', "'", markdown)

    markdown = re.sub(r'\n{4,}', '\n\n\n', markdown)

    return markdown.strip()


def download_image(url: str, assets_dir: str) -> str:
    os.makedirs(assets_dir, exist_ok=True)
    ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
    if len(ext) > 6 or "." not in ext:
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(assets_dir, filename)

    headers = {
        "User-Agent": WECHAT_UA,
        "Referer": "https://mp.weixin.qq.com/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        print(f"  [WARN] 图片下载失败: {url[:60]}... ({e})", file=sys.stderr)
        return url

    return filepath


def build_file_path(output_dir: str, author: str, title: str, publish_date: str) -> str:
    year = datetime.now().strftime("%Y年")
    if publish_date:
        try:
            dt = None
            for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y年%m月%d日"]:
                try:
                    dt = datetime.strptime(publish_date, fmt)
                    break
                except ValueError:
                    continue
            if dt:
                year = dt.strftime("%Y年")
                date_str = dt.strftime("%Y年%m月%d日")
            else:
                date_str = publish_date.replace(" ", "").replace(":", "-")
        except Exception:
            date_str = publish_date.replace(" ", "").replace(":", "-")
    else:
        date_str = datetime.now().strftime("%Y年%m月%d日")

    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
    safe_author = re.sub(r'[\\/:*?"<>|]', "_", author)
    filename = f"{date_str}-{safe_title}.md"
    return os.path.join(output_dir, year, safe_author, filename)


def format_yaml_frontmatter(meta: dict) -> str:
    return (
        "---\n"
        f"标题: \"{meta['title']}\"\n"
        f"作者: \"{meta['author']}\"\n"
        f"发布时间: \"{meta['publish_date']}\"\n"
        f"来源: 公众号\n"
        f"url: \"{meta.get('url', '')}\"\n"
        f"存档时间: \"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"\n"
        "---\n"
    )


def main():
    parser = argparse.ArgumentParser(description="抓取公众号文章")
    parser.add_argument("url", help="公众号文章链接")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--assets-dir", default=None)
    args = parser.parse_args()
    args.output_dir = os.path.expanduser(args.output_dir)

    print(f"[INFO] 正在抓取: {args.url}", file=sys.stderr)
    html = fetch_page(args.url)

    print("[INFO] 解析元数据...", file=sys.stderr)
    meta = extract_meta(html)
    meta["url"] = args.url
    print(f"  标题: {meta['title']}", file=sys.stderr)
    print(f"  作者: {meta['author']}", file=sys.stderr)
    print(f"  时间: {meta['publish_date']}", file=sys.stderr)

    file_path = build_file_path(
        args.output_dir, meta["author"], meta["title"], meta["publish_date"]
    )
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    pub_date = meta.get("publish_date", "")
    asset_subdir = pub_date[:10] if pub_date and len(pub_date) >= 10 else datetime.now().strftime("%Y-%m-%d")

    if args.assets_dir:
        assets_dir = args.assets_dir
    else:
        assets_dir = os.path.join(
            os.path.dirname(file_path), DEFAULT_ASSETS_DIR_NAME, asset_subdir
        )

    meta["assets_dir"] = assets_dir

    print("[INFO] 提取正文...", file=sys.stderr)
    print("[INFO] 下载图片中...", file=sys.stderr)
    content = extract_content(html, assets_dir, file_path)

    # Output structured data for the opencode agent
    output = {
        "meta": meta,
        "content": content,
        "file_path": os.path.normpath(file_path),
        "assets_dir": os.path.normpath(assets_dir),
    }

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
