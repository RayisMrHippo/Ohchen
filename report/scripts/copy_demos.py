import shutil
from pathlib import Path

src_dir = Path.home() / 'Pictures' / 'Screenshots'
dst_dir = Path('report/assets')

# 刪除剛才複製的
for f in dst_dir.glob('demo-*.png'):
    f.unlink()

# 用 2026-06-24 的截圖（今天的）
files = sorted([f for f in src_dir.glob('*.png') if '2026-06-24' in f.name], key=lambda f: f.stat().st_size, reverse=True)
print("Today's screenshots:")
for f in files:
    print(f"  {f.name} ({f.stat().st_size} bytes)")

# 取最大的 2 張
for i, f in enumerate(files[:2], 1):
    dst = dst_dir / f'demo-{i:02d}.png'
    shutil.copy(f, dst)
    print(f"Copied: {f.name} -> {dst.name}")