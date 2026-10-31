# -*- coding: utf-8 -*-
"""视频流程的分镜契约。

复制到项目里改名为 `script_data.py`，替换示例内容。
`flatten()` 必须返回包含以下字段的 dict：
  id, scene, text, sub, big, layout, accent, eyebrow, img, note, clip

beat 元组（后三项可省）：
  (口播, 字幕, 大字, 版式, 主色, 小标签, 图片, 数据卡说明, 是否用动态片段)

版式（layout）：
  card    图片卡（16:9 铺满；超宽横幅自动走深色卡底）
  poster  竖构图/近方形插画：卡片按图收窄，图铺满卡片（配合 image_margins.py 裁空白边）
  text    纯文字卡（引语/观点）
  data    数据卡（主数字 count-up + 说明行）
  hook    全屏大字钩子
  full    更高的图片卡
  bleed   整屏动态片段（第 9 位写片段 key）

图片路径：`render.py` 先找 `--assets` 目录，找不到再回落到项目 `assets/`。
原素材只读引用；用 `python image_margins.py ../06 --crop` 裁过空白边的衍生图放 `assets/`，
beat 里直接写衍生文件名（如 `file-xxx_crop.png`）。
"""

# 先定主题句和三个支撑问题，再写 SCENES（见 SKILL.md 阶段 1）。
# 主题句 = 观众看完要记住的那句话；ROADMAP = 主题句拆出的三个追问。
THESIS = "观众看完要记住的那句话"
ROADMAP = ["这是什么钱", "谁在付", "它什么时候会停"]

IMG = {
    "cover": "file-20260101000000000.png",   # 文章同目录下的本地图片
    "detail": "file-20260101000000001.png",
}

# 可选：参考视频（相对本目录）。文章没有配图、或想加真实运动镜头时用。
# 选片段前先跑 `python video_sheet.py --video ../03/01.mp4` 看镜头区间。
VIDEO_SRC = "../03/01.mp4"

# beat_id -> 源片上的 (起点, 终点)，单位秒；不要跨剪辑点，也不要配原片人声。
CLIP_SRC = {
    "00_00": (0.15, 3.30),
    "01_02": (23.00, 25.50),
}

SCENES = [
    {
        "id": "hook",
        "label": "00 / 开场",          # 显示在左上角
        "kind": "hook",
        "default_img": IMG["cover"],
        "beats": [
            # 第 9 位 True：这个镜头用同名动态片段（clips/00_00/）
            ("一个 AI，为了查清公园门口谁人多，连轴转了十一天。",
             "一个 AI，为了查清\n公园门口谁人多\n连轴转了 11 天",
             "11 天", "hook", "orange", "真实事件", IMG["cover"], "", True),
            ("被风控封了，就自己找密钥。",
             "被风控封了\n就自己找密钥",
             "被封之后", "hook", "cyan", "越界操作", IMG["detail"]),
        ],
    },
    {
        "id": "data",
        "label": "01 / 数字",
        "kind": "story",
        "default_img": None,
        "beats": [
            # 竖构图插画：先用 image_margins.py 裁掉空白边，再用 poster 让图铺满卡片
            ("它之所以值钱，是因为没人能一句话说清它怎么坏的。",
             "没人能一句话说清\n它怎么坏的",
             "说不清", "poster", "cyan", "竖构图", "cover_crop.png"),
            # 第 8 位是数据卡说明行，count-up 结束后显示在数字下面
            ("报告说，至少 35,300 次网络请求。",
             "报告：至少 35,300 次网络请求",
             "35,300", "data", "orange", "请求量", None,
             "份安全报告里的数字"),
            ("数字有争议，但都不是随便点两下。",
             "数字有争议\n但都不是随便点两下",
             "都不是点两下", "data", "cyan", "数字争议", None,
             "腾讯方面给出的另一组口径"),
        ],
    },
]


def flatten(scenes=None):
    scenes = SCENES if scenes is None else scenes
    out = []
    for si, sc in enumerate(scenes):
        for bi, b in enumerate(sc["beats"]):
            text, sub, big, layout, accent, eyebrow = b[:6]
            img = b[6] if len(b) > 6 else None
            if img is None:
                img = (sc.get("beat_imgs") or [None] * len(sc["beats"]))[bi] \
                      or sc.get("default_img")
            note = b[7] if len(b) > 7 else ""
            # 片段目录按 beat id 命名；render.py 读 clips/<id>/meta.json
            clip = f"{si:02d}_{bi:02d}" if len(b) > 8 and b[8] else ""
            out.append({
                "id": f"{si:02d}_{bi:02d}",
                "scene": si,
                "text": text,
                "sub": sub,
                "big": big,
                "layout": layout,       # hook | card | poster | text | data | full
                "accent": accent,       # orange | cyan
                "eyebrow": eyebrow,
                "img": img,
                "note": note,
                "clip": clip,
            })
    return out


if __name__ == "__main__":
    beats = flatten()
    chars = sum(len(b["text"]) for b in beats)
    clips = [b["id"] for b in beats if b["clip"]]
    print("beats", len(beats), "chars", chars, "est", f"{chars / 5.7 / 60:.1f}min",
          "clips", len(clips))
