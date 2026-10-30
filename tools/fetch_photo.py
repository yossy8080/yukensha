"""記事の写真を1枚取ってきて、サイト用のJPEGにする（Hermesが写真を入れるときに使う）。

使い方: python tools/fetch_photo.py 画像のURL 保存先.jpg [--referer 写真が載っているページのURL]
        python tools/fetch_photo.py 手元の画像ファイル 保存先.jpg   （手元のファイルも同じように直す）
- 本当に画像か Pillow で確かめる
- 長い辺を 1600px までに縮め、RGB の JPEG（画質82）にする。EXIF（撮影情報・位置情報など）は捨てる
- うまくいけば「OK 幅x高さ バイト数」、だめなら「NG 理由」（終了コード1）
"""
import io
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

MAX_SIDE = 1600
QUALITY = 82
TIMEOUT = 30
MAX_BYTES = 30 * 1024 * 1024  # 大きすぎるファイルは取らない
# 府省のサイトには、ふつうのブラウザに見えないと 403 を返すところがあるので、ブラウザと同じ名乗りにする
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def download(url: str, referer: str = "") -> bytes:
    headers = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
               "Accept-Language": "ja,en;q=0.8"}
    if referer:
        headers["Referer"] = referer
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("ファイルが大きすぎます")
    return data


def convert(data: bytes) -> tuple[bytes, int, int]:
    """画像か確かめて、向きを直し、縮めて、EXIF なしの JPEG にする。"""
    try:
        Image.open(io.BytesIO(data)).verify()  # 壊れた画像・画像でないもの（HTMLのエラーページなど）はここで落ちる
    except Exception as e:
        raise ValueError(f"画像ではありません（{type(e).__name__}）")
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)  # スマホ写真の回転を反映してから EXIF を捨てる
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))  # 透明な部分は白にする
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    else:
        im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)  # exif を渡さないので付かない
    return out.getvalue(), im.width, im.height


def main(argv: list[str]) -> int:
    args = list(argv)
    referer = ""
    if "--referer" in args:
        i = args.index("--referer")
        if i + 1 >= len(args):
            print("NG --referer のあとにURLがありません")
            return 1
        referer = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        print("NG 使い方: python tools/fetch_photo.py 画像のURLまたはファイル 保存先.jpg [--referer URL]")
        return 1
    src, dest = args
    try:
        if src.startswith(("http://", "https://")):
            data = download(src, referer)
        else:
            p = Path(src)
            if not p.is_file():
                raise ValueError(f"ファイルが見つかりません: {src}")
            data = p.read_bytes()
        jpg, w, h = convert(data)
        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(jpg)
    except Exception as e:
        print(f"NG {e}")
        return 1
    print(f"OK {w}x{h} {len(jpg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
