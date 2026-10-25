"""省庁エンブレム用の字形データを作る（3D の押し出し文字に使う）。

使い方:  python tools/make_glyphs.py path/to/ShipporiMincho-ExtraBold.ttf
出力:    assets/glyphs.json  {"字": {"d": "SVGパス", "adv": 送り幅}, ...}  (1em = 1000)
フォント: Shippori Mincho (SIL Open Font License 1.1)
"""
import json, sys, pathlib
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
chars = set("有権者省庁国会")
for s in src:
    chars |= set(s["name"]) | set(s.get("emblem", ""))
font = TTFont(sys.argv[1])
cmap = font.getBestCmap()
gs = font.getGlyphSet()
upm = font["head"].unitsPerEm
out = {}
for ch in sorted(chars):
    g = cmap.get(ord(ch))
    if not g:
        continue
    pen = SVGPathPen(gs)
    # y を反転（SVG 座標）し 1000 単位にそろえる
    k = 1000 / upm
    gs[g].draw(TransformPen(pen, (k, 0, 0, -k, 0, 880)))
    out[ch] = {"d": pen.getCommands(), "adv": round(gs[g].width * k)}
(ROOT / "assets/glyphs.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(len(out), "glyphs ->", ROOT / "assets/glyphs.json")
