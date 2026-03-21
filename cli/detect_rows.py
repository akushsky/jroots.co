"""
detect_rows.py — нарезка страниц ведомости на строки.

Алгоритм (valley-based):
  1. Grayscale → профиль тёмных пикселей по y
  2. Сглаживаем профиль (rolling mean)
  3. Ищем «долины» — промежутки с малым количеством тёмных пикселей
     между «горками» (строками текста)
  4. Граница строки — середина каждой долины
  5. Отфильтровываем строки вне зоны данных и слишком маленькие/большие

Использование:
  python cli/detect_rows.py --case 680-1-4
  python cli/detect_rows.py --case 680-1-4 --show-debug
  python cli/detect_rows.py --page path/to/page.png
"""

import json
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

BASE_DIR = Path("cli/dazho_downloads")

# ── Параметры ────────────────────────────────────────────────────────────────
DARK_THRESH   = 130    # пиксель темнее → тёмный
X_FRAC_START  = 0.05   # левая граница зоны анализа (доля ширины)
X_FRAC_END    = 0.45   # правая граница (имена + цифры, не правая рамка)
VALLEY_THRESH = 0.03   # доля тёмных пикселей ниже этого → «долина» (межстрочье)
MIN_ROW_H     = 40     # минимальная высота строки данных
MAX_ROW_H     = 180    # максимальная высота строки данных
ROW_PADDING   = 3      # отступ при нарезке


def _dark_profile(img: Image.Image) -> list[float]:
    """Возвращает для каждой y-координаты долю тёмных пикселей в зоне имён."""
    gray = img.convert("L")
    w, h = gray.size
    import numpy as np
    arr = np.array(gray)
    x0 = int(w * X_FRAC_START)
    x1 = int(w * X_FRAC_END)
    zone = arr[:, x0:x1]
    dark = (zone < DARK_THRESH).sum(axis=1) / (x1 - x0)
    return dark.tolist()


def _smooth(profile: list[float], window: int = 3) -> list[float]:
    """Simple moving average."""
    result = []
    for i in range(len(profile)):
        lo = max(0, i - window)
        hi = min(len(profile), i + window + 1)
        result.append(sum(profile[lo:hi]) / (hi - lo))
    return result


def detect_row_boundaries(img: Image.Image) -> list[int]:
    """
    Возвращает список y-координат разделителей строк
    (центры «долин» между строками текста).
    """
    h = img.height
    profile = _dark_profile(img)
    smoothed = _smooth(profile, window=4)

    # Найти переходы: долина → горка → долина
    in_valley = [v < VALLEY_THRESH for v in smoothed]

    # Группируем долины
    valley_groups = []
    i = 0
    while i < h:
        if in_valley[i]:
            j = i
            while j < h and in_valley[j]:
                j += 1
            valley_groups.append((i, j - 1))
            i = j
        else:
            i += 1

    # Центр каждой долины = граница строки
    boundaries = [int((a + b) / 2) for a, b in valley_groups]
    return boundaries, profile


def _is_empty_strip(crop: Image.Image, threshold: float = 0.02) -> bool:
    """Check if a row strip is essentially empty (border, blank space, etc.)."""
    import numpy as np
    gray = crop.convert("L")
    arr = np.array(gray)
    w = arr.shape[1]
    x0 = int(w * X_FRAC_START)
    x1 = int(w * X_FRAC_END)
    zone = arr[:, x0:x1]
    dark_frac = (zone < DARK_THRESH).sum() / zone.size
    return dark_frac < threshold


def crop_rows(img: Image.Image, boundaries: list[int]) -> list[tuple[int, int, Image.Image]]:
    """Нарезает строки между границами. Возвращает [(y1, y2, crop), ...]."""
    h = img.height
    w = img.width
    segs = list(zip([0] + boundaries, boundaries + [h]))
    rows = []
    for y_top, y_bot in segs:
        rh = y_bot - y_top
        if rh < MIN_ROW_H or rh > MAX_ROW_H:
            continue
        y1 = max(0, y_top + ROW_PADDING)
        y2 = min(h, y_bot - ROW_PADDING)
        if y2 - y1 < MIN_ROW_H // 2:
            continue
        crop = img.crop((0, y1, w, y2))
        if _is_empty_strip(crop):
            continue
        rows.append((y1, y2, crop))
    return rows


def process_page(img_path: Path, out_dir: Path, debug: bool = False):
    """
    Обрабатывает одну страницу: детектирует строки, сохраняет стрипы.
    Возвращает (saved_paths, boundaries, rows).
    """
    img = Image.open(img_path)
    boundaries, profile = detect_row_boundaries(img)

    if debug:
        debug_img = img.copy().convert("RGB")
        draw = ImageDraw.Draw(debug_img)
        for y in boundaries:
            draw.line([(0, y), (img.width, y)], fill=(255, 0, 0), width=2)
        debug_path = out_dir / f"{img_path.stem}_debug.png"
        debug_img.save(debug_path)
        print(f"  Debug: {debug_path} ({len(boundaries)} boundaries)")

    rows = crop_rows(img, boundaries)
    saved = []
    for idx, (y1, y2, crop) in enumerate(rows):
        row_path = out_dir / f"{img_path.stem}_row{idx+1:02d}.png"
        crop.save(row_path)
        saved.append(row_path)

    return saved, boundaries, rows


def process_case(case_id: str, debug: bool = False) -> dict:
    """
    Обрабатывает все страницы дела. Возвращает маппинг page→[row_paths].
    """
    pages_dir = BASE_DIR / f"{case_id}_pages"
    out_dir   = BASE_DIR / f"{case_id}_rows"
    out_dir.mkdir(exist_ok=True)

    skip_names = {
        "page_001.png", "page_002.png",
        "page-001.png", "page-002.png",
        "page-01.png", "page-02.png",
    }
    images = sorted(p for p in pages_dir.glob("*.png")
                    if p.name not in skip_names)

    result = {}
    total_rows = 0

    for img_path in images:
        saved, lines, rows = process_page(img_path, out_dir, debug=debug)
        result[img_path.name] = [str(p) for p in saved]
        total_rows += len(saved)
        print(f"  {img_path.name}: {len(lines)} lines → {len(saved)} rows")

    # Сохраняем манифест
    manifest_path = BASE_DIR / f"{case_id}_rows_manifest.json"
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"\nTotal: {len(images)} pages, {total_rows} row strips → {out_dir}")
    print(f"Manifest: {manifest_path}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Detect table rows and crop strips from ledger pages")
    parser.add_argument("--case", default="680-1-4", help="Case ID")
    parser.add_argument("--page", default="", help="Process single page (path to PNG)")
    parser.add_argument("--show-debug", action="store_true",
                        help="Save debug images with detected lines marked red")
    parser.add_argument("--dark-thresh", type=int, default=DARK_THRESH)
    parser.add_argument("--valley-thresh", type=float, default=VALLEY_THRESH)
    args = parser.parse_args()

    if args.page:
        img_path = Path(args.page)
        out_dir = img_path.parent / f"{img_path.stem}_rows"
        out_dir.mkdir(exist_ok=True)
        saved, lines, rows = process_page(img_path, out_dir, debug=True)
        print(f"Detected {len(lines)} lines, saved {len(saved)} strips to {out_dir}")
        for i, (y1, y2, _) in enumerate(rows):
            print(f"  row {i+1:2d}: y={y1}..{y2} (h={y2-y1})")
    else:
        process_case(args.case, debug=args.show_debug)


if __name__ == "__main__":
    main()
