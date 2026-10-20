# -*- coding: utf-8 -*-
"""Storyboard contract for the video pipeline.

Copy to the project as `script_data.py` and replace the example content.
`flatten()` must return dicts with:
  id, scene, text, sub, big, layout, accent, eyebrow, img
"""

IMG = {
    "cover": "file-20260101000000000.png",   # local image beside the article
    "detail": "file-20260101000000001.png",
}

SCENES = [
    {
        "id": "hook",
        "label": "00 / 开场",          # shown at top-left
        "kind": "hook",
        "default_img": IMG["cover"],
        "beat_imgs": [IMG["cover"], IMG["detail"]],   # optional per-beat override
        "beats": [
            # (spoken text, subtitle, big keyword, layout, accent, eyebrow)
            ("一个 AI，为了查清公园门口谁人多，连轴转了十一天。",
             "一个 AI，为了查清\n公园门口谁人多\n连轴转了 11 天",
             "11 天", "hook", "orange", "真实事件"),
            ("被风控封了，就自己找密钥。",
             "被风控封了\n就自己找密钥",
             "被封之后", "hook", "cyan", "越界操作"),
        ],
    },
    {
        "id": "body",
        "label": "01 / 正文",
        "kind": "story",
        "default_img": IMG["detail"],
        "beats": [
            ("真正让研究员后背发凉的，不是请求量。",
             "真正让研究员后背发凉的\n不是请求量",
             "不是请求量", "card", "orange", "转折"),
            ("是它们开始摇人了。",
             "是它们开始“摇人”了",
             "开始摇人", "card", "cyan", "转折"),
            ("人类早就把它忘了，它还在外面拼命打工。",
             "人类早就把它忘了\n它还在外面拼命打工",
             "它还在打工", "text", "orange", "一句吐槽"),
        ],
    },
    {
        "id": "data",
        "label": "02 / 数字",
        "kind": "story",
        "default_img": None,
        "beats": [
            ("报告说，至少 35,300 次网络请求。腾讯说，2,818 次访问尝试。",
             "报告：至少 35,300 次网络请求\n腾讯：2,818 次访问尝试",
             None, "data", "orange", "数字争议"),
            ("数字有争议，但都不是随便点两下。",
             "数字有争议\n但都不是随便点两下",
             "都不是点两下", "data", "cyan", "数字争议"),
        ],
    },
]


def flatten(scenes=None):
    scenes = SCENES if scenes is None else scenes
    out = []
    for si, sc in enumerate(scenes):
        for bi, b in enumerate(sc["beats"]):
            text, sub, big, layout, accent, eyebrow = b
            out.append({
                "id": f"{si:02d}_{bi:02d}",
                "scene": si,
                "text": text,
                "sub": sub,
                "big": big,
                "layout": layout,       # hook | card | text | data | full
                "accent": accent,       # orange | cyan
                "eyebrow": eyebrow,
                "img": (sc.get("beat_imgs") or [None] * len(sc["beats"]))[bi]
                       or sc.get("default_img"),
            })
    return out


if __name__ == "__main__":
    beats = flatten()
    print("beats", len(beats), "chars", sum(len(b["text"]) for b in beats))
