/* 有権者 — 都道府県の地図データ（data/prefmap.json）を読む（ES module。3D 地図と、3D が使えないときの SVG 地図の両方で使う）
   data/prefmap.json は tools/make_prefmap.py で作る。座標は「東経137度・北緯36度」を中心にした平面（1 = 緯度1度。y は北が大きい）。
   API: decodeMap(raw) -> { prefs: {id: {c: [x, y], polys: [[外周 Float32Array, 穴...], ...], box: [x0, y0, x1, y1]}}, box, inset: {box} }
        hitTest(dec, x, y, tol) -> その点の都道府県 id（どこにも入っていなければ、tol 以内でいちばん近い都道府県。無ければ null） */

export function decodeMap(raw) {
  const S = raw.scale;
  const prefs = {};
  const box = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [id, v] of Object.entries(raw.prefs)) {
    const pb = [Infinity, Infinity, -Infinity, -Infinity];
    const polys = v.p.map((poly) => poly.map((r) => {
      const a = new Float32Array(r.length);
      let x = 0, y = 0;
      for (let i = 0; i < r.length; i += 2) {
        x += r[i];
        y += r[i + 1];
        a[i] = x / S;
        a[i + 1] = y / S;
        if (a[i] < pb[0]) pb[0] = a[i];
        if (a[i + 1] < pb[1]) pb[1] = a[i + 1];
        if (a[i] > pb[2]) pb[2] = a[i];
        if (a[i + 1] > pb[3]) pb[3] = a[i + 1];
      }
      return a;
    }));
    prefs[id] = { c: [v.c[0] / S, v.c[1] / S], polys, box: pb };
    box[0] = Math.min(box[0], pb[0]); box[1] = Math.min(box[1], pb[1]);
    box[2] = Math.max(box[2], pb[2]); box[3] = Math.max(box[3], pb[3]);
  }
  return { prefs, box, inset: { box: raw.inset.box.map((v) => v / S) } };
}

function inRing(r, x, y) {
  let inside = false;
  for (let i = 0, j = r.length - 2; i < r.length; j = i, i += 2) {
    const xi = r[i], yi = r[i + 1], xj = r[j], yj = r[j + 1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function ringDist2(r, x, y) {
  let best = Infinity;
  for (let i = 0, j = r.length - 2; i < r.length; j = i, i += 2) {
    const ax = r[j], ay = r[j + 1], dx = r[i] - ax, dy = r[i + 1] - ay;
    const L = dx * dx + dy * dy;
    const t = L ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / L)) : 0;
    const ex = ax + t * dx - x, ey = ay + t * dy - y;
    const d = ex * ex + ey * ey;
    if (d < best) best = d;
  }
  return best;
}

export function hitTest(dec, x, y, tol = 0) {
  let near = null, nearD = tol * tol;
  for (const id in dec.prefs) {
    const p = dec.prefs[id], b = p.box;
    if (x < b[0] - tol || x > b[2] + tol || y < b[1] - tol || y > b[3] + tol) continue;
    for (const poly of p.polys) {
      if (inRing(poly[0], x, y)) {
        let hole = false;
        for (let k = 1; k < poly.length; k++) if (inRing(poly[k], x, y)) hole = true;
        if (!hole) return id;
      }
      if (tol > 0) {
        const d = ringDist2(poly[0], x, y);
        if (d < nearD) { nearD = d; near = id; }
      }
    }
  }
  return near;
}
