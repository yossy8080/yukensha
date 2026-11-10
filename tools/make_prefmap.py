"""有権者：地方ページ（local.html）の日本地図のデータを作る

使い方: python tools/make_prefmap.py 元のTopoJSON data/prefmap.json
  元のTopoJSON = スマートニュース メディア研究所「japan-topography」の都道府県ファイル
  （data/municipality/topojson/s0010/prefectures.json。国土数値情報（行政区域データ）を加工したもの）
  https://github.com/smartnews-smri/japan-topography

やること:
  1. 境界線（TopoJSON の arc）を1本ずつ簡単にする（隣の県と同じ線を使うので、県と県のあいだにすき間ができない）
  2. とても小さい島は省く（各県のいちばん大きい陸地は必ず残す）。東京都の小笠原諸島など北緯30度より南の島も省く
  3. 沖縄県と、鹿児島県の北緯30度より南の島（奄美・トカラ）は、左上の枠（はめ込み）に移す
  4. 経度・緯度を平面の座標に直し（中心 東経137度・北緯36度）、1000倍の整数にして差分で書く
出力: {"scale", "lon0", "lat0", "inset": {"box", "dx", "dy"}, "prefs": {id: {"c": [x, y], "p": [[外周, 穴...], ...]}}}
  リングは [x0, y0, dx1, dy1, ...]（2点目からは前の点との差）。y は北が大きい。
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LON0, LAT0 = 137.0, 36.0
KX = math.cos(math.radians(LAT0))
SCALE = 1000
EPS = 0.006          # 簡単にする度合い（平面の座標で。0.006 ≒ 670m）
MIN_AREA = 0.0016    # これより小さい島は省く（平面の座標の面積。≒ 20km²）
SOUTH_CUT = 30.0     # 東京都はこれより南の島を省く／鹿児島県はこれより南の島をはめ込みへ
INSET_DX, INSET_DY = 6.2, 14.6  # はめ込みへの移動量（平面の座標）


def proj(lon, lat):
    return ((lon - LON0) * KX, lat - LAT0)


def decode_arcs(topo):
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    out = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append(proj(x * sx + tx, y * sy + ty))
        out.append(pts)
    return out


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def dp(pts, eps):
    """Douglas-Peucker（端の点は必ず残す）"""
    if len(pts) <= 2:
        return pts[:]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        best, bi = 0, -1
        for k in range(i + 1, j):
            d = seg_dist(pts[k], pts[i], pts[j])
            if d > best:
                best, bi = d, k
        if best > eps and bi > 0:
            keep[bi] = True
            stack.append((i, bi))
            stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def simplify_arc(pts, eps):
    if len(pts) > 3 and pts[0] == pts[-1]:
        # 閉じた線（島1つが1本の線）：始点からいちばん遠い点で2つに分けて簡単にする
        far = max(range(len(pts)), key=lambda k: math.hypot(pts[k][0] - pts[0][0], pts[k][1] - pts[0][1]))
        return dp(pts[: far + 1], eps)[:-1] + dp(pts[far:], eps)
    return dp(pts, eps)


def ring_of(idx, arcs):
    out = []
    for a in idx:
        pts = arcs[a] if a >= 0 else arcs[~a][::-1]
        out.extend(pts if not out else pts[1:])
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def area(r):
    s = 0.0
    for i in range(len(r)):
        x0, y0 = r[i]
        x1, y1 = r[(i + 1) % len(r)]
        s += x0 * y1 - x1 * y0
    return s / 2


def centroid(r):
    a = area(r)
    if abs(a) < 1e-12:
        return r[0]
    cx = cy = 0.0
    for i in range(len(r)):
        x0, y0 = r[i]
        x1, y1 = r[(i + 1) % len(r)]
        f = x0 * y1 - x1 * y0
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    return (cx / (6 * a), cy / (6 * a))


def enc(r):
    q = [(round(x * SCALE), round(y * SCALE)) for x, y in r]
    # 整数にして重なった点は除く
    qq = [q[0]]
    for p in q[1:]:
        if p != qq[-1]:
            qq.append(p)
    if len(qq) > 1 and qq[-1] == qq[0]:
        qq.pop()
    if len(qq) < 3:
        return None
    flat = [qq[0][0], qq[0][1]]
    for (x0, y0), (x1, y1) in zip(qq, qq[1:]):
        flat += [x1 - x0, y1 - y0]
    return flat


def main(src, dst):
    topo = json.loads(Path(src).read_text(encoding="utf-8"))
    prefs = json.loads((ROOT / "data" / "prefectures.json").read_text(encoding="utf-8"))
    by_name = {p["name"]: p["id"] for p in prefs}
    arcs = [simplify_arc(a, EPS) for a in decode_arcs(topo)]
    lat_of = lambda y: y + LAT0
    out, total = {}, 0
    inset_pts = []
    for g in list(topo["objects"].values())[0]["geometries"]:
        pid = by_name[g["properties"]["N03_001"]]
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        rings = []
        for poly in polys:
            rs = [ring_of(r, arcs) for r in poly]
            if len(rs[0]) < 3:
                continue
            rings.append(rs)
        big = max(rings, key=lambda rs: abs(area(rs[0])))
        keep = []
        for rs in rings:
            a = abs(area(rs[0]))
            cy = lat_of(centroid(rs[0])[1])
            if rs is not big and a < MIN_AREA:
                continue
            if pid == "tokyo" and cy < SOUTH_CUT:
                continue
            moved = pid == "okinawa" or (pid == "kagoshima" and cy < SOUTH_CUT)
            if moved:
                rs = [[(x + INSET_DX, y + INSET_DY) for x, y in r] for r in rs]
                inset_pts += rs[0]
            keep.append(rs)
        big = max(keep, key=lambda rs: abs(area(rs[0])))
        c = centroid(big[0])
        enc_polys = []
        for rs in keep:
            # 外周は反時計回り、穴は時計回りにそろえる
            fixed = []
            for k, r in enumerate(rs):
                ccw = area(r) > 0
                if (k == 0) != ccw:
                    r = r[::-1]
                e = enc(r)
                if e:
                    fixed.append(e)
                    total += len(e) // 2
            if fixed:
                enc_polys.append(fixed)
        out[pid] = {"c": [round(c[0] * SCALE), round(c[1] * SCALE)], "p": enc_polys}
    xs = [p[0] for p in inset_pts]
    ys = [p[1] for p in inset_pts]
    m = 0.25
    box = [round((min(xs) - m) * SCALE), round((min(ys) - m) * SCALE), round((max(xs) + m) * SCALE), round((max(ys) + m) * SCALE)]
    data = {
        "credit": "国土数値情報（行政区域データ）（国土交通省）をもとに、スマートニュース メディア研究所「japan-topography」が簡素化したものを、有権者がさらに加工",
        "scale": SCALE, "lon0": LON0, "lat0": LAT0,
        "inset": {"box": box, "dx": round(INSET_DX * SCALE), "dy": round(INSET_DY * SCALE)},
        "prefs": {p["id"]: out[p["id"]] for p in prefs},
    }
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    Path(dst).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"OK {len(out)}都道府県 {total}点 {len(text.encode('utf-8'))}バイト")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("使い方: python tools/make_prefmap.py 元のTopoJSON 出力.json")
    main(sys.argv[1], sys.argv[2])
