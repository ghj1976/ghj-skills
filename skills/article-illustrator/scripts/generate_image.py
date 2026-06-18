import json
import base64
import os
import sys
import argparse
import urllib.request
import urllib.error


def call_api(api_key, prompt, size="1024x768"):
    url = "https://apihub.agnes-ai.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "size": size,
        "return_base64": True,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        resp_data = json.loads(response.read().decode("utf-8"))

    try:
        b64 = resp_data["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError):
        error_msg = resp_data.get("error", {}).get("message", resp_data)
        raise ValueError(f"API 响应异常: {error_msg}")

    if not b64:
        error_msg = resp_data.get("error", {}).get("message", "b64_json 为空")
        raise ValueError(f"API 返回错误: {error_msg}")

    return b64


def save_image(b64_string, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(b64_string))


def save_prompt(text, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    parser = argparse.ArgumentParser(description="文章配图生成工具")
    parser.add_argument("--prompt", required=True, help="图片描述提示词（英文）")
    parser.add_argument("--filename", required=True, help="文件名（不含扩展名），如 01-concept-comparison")
    parser.add_argument("--output-dir", default="./imgs", help="输出目录，默认 ./imgs")
    parser.add_argument("--size", default="1024x768", help="图片尺寸，默认 1024x768")
    parser.add_argument("--retries", type=int, default=1, help="失败重试次数，默认 1")
    args = parser.parse_args()

    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        print("错误: 请设置环境变量 AGNES_API_KEY")
        sys.exit(1)

    prompt_path = os.path.join(args.output_dir, "prompts", f"{args.filename}.md")
    image_path = os.path.join(args.output_dir, f"{args.filename}.png")

    save_prompt(args.prompt, prompt_path)
    print(f"提示词已保存: {prompt_path}")

    last_error = None
    for attempt in range(1 + args.retries):
        try:
            print(f"生成图片中（第 {attempt + 1} 次）...")
            b64 = call_api(api_key, args.prompt, args.size)
            save_image(b64, image_path)
            print(f"图片已保存: {image_path}")
            return
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
            print(f"  失败: {last_error}")
        except urllib.error.URLError as e:
            last_error = f"网络错误: {e.reason}"
            print(f"  失败: {last_error}")
        except ValueError as e:
            last_error = str(e)
            print(f"  失败: {last_error}")
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            last_error = f"响应解析错误: {e}"
            print(f"  失败: {last_error}")

        if attempt < args.retries:
            print("  重试中...")

    print(f"错误: 图片生成失败，已重试 {args.retries} 次")
    print(f"最后错误: {last_error}")
    sys.exit(1)


if __name__ == "__main__":
    main()
