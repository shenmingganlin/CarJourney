"""
车之旅 v2.0
  · 无燃油限制，纯距离冲刺
  · 多层视差背景：云朵 / 山脉 / 月面星星 / 火山烟雾
  · 精细车辆渲染：高光 / 阴影 / 轮弧 / 破坏状态
  · 翻车连击系统 · 加速板 · 路障
  · 全新 HUD：速度 / 连击 / 距离

操控：→ 油门  ← 刹车/倒车  ↑↓ 空中倾斜  空格 紧急制动
      R 重开  ESC 暂停  M 返回菜单
"""

import json, math, os, random, sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import pygame

pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=256)

# ════════════════════════════ 基本常量 ════════════════════════════
W, H     = 1280, 720
FPS      = 60
DT       = 1 / FPS
SUBSTEPS = 4
SUB_DT   = DT / SUBSTEPS
# ── 路径辅助：区分"只读资源"和"可写用户数据" ──
# PyInstaller --onefile 打包后，sys.frozen=True，资源被解压到临时目录 sys._MEIPASS
# 用户数据（番茄钟日志、节拍缓存、Music 文件夹）必须存到 exe 旁边的固定位置
def _resource_dir():
    """只读资源目录（assets/icon 等打包内容）"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


def _user_data_dir():
    """用户数据目录（可写、跨启动持久化）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent   # exe 旁边
    return Path(__file__).parent             # 源码同级


DATA_DIR = _user_data_dir() / "data"
DATA_DIR.mkdir(exist_ok=True)
POMO_LOG_PATH   = DATA_DIR / "pomodoro_log.json"
BEAT_CACHE_PATH = DATA_DIR / "beat_cache.json"
PPM      = 30.0   # pixels per meter

# ════════════════════════════ 颜色 ════════════════════════════════
class C:
    BLACK  = (8,   8,  12)
    WHITE  = (245, 245, 250)
    GRAY   = (120, 125, 135)
    DGRAY  = (30,  33,  42)
    RED    = (232, 62,  70)
    ORG    = (255, 145, 45)
    YEL    = (255, 215, 52)
    GRN    = (75,  200, 95)
    BLU    = (70,  150, 236)
    CYN    = (88,  210, 215)
    PINK   = (245, 108, 148)
    SKIN   = (255, 196, 155)
    BOOST  = (85,  255, 160)
    LAVA   = (255, 95,  25)


def lerpC(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def lerp(a, b, t):
    return a + (b - a) * t


# ════════════════════════════ 场景定义 ════════════════════════════
BIOMES = [
    dict(
        name="GRASSLAND", label="草原",
        sky_a=(65, 155, 220), sky_b=(168, 215, 248),
        g0=(88, 178, 76), g1=(62, 130, 52), g2=(40, 82, 34),
        mtn_a=(55, 105, 52), mtn_b=(75, 138, 70),
        cloud_col=(255, 255, 255), glow=None,
        gravity=1.0, friction=0.78, amp=160, freq=0.014, mood="day",
    ),
    dict(
        name="DESERT", label="沙漠",
        sky_a=(218, 148, 62), sky_b=(255, 210, 115),
        g0=(218, 182, 112), g1=(190, 152, 85), g2=(158, 120, 60),
        mtn_a=(200, 162, 88), mtn_b=(222, 178, 106),
        cloud_col=(255, 235, 185), glow=(255, 210, 80),
        gravity=1.0, friction=0.72, amp=200, freq=0.010, mood="desert",
    ),
    dict(
        name="ICE", label="冰原",
        sky_a=(148, 188, 228), sky_b=(208, 232, 255),
        g0=(202, 228, 255), g1=(155, 192, 228), g2=(112, 152, 205),
        mtn_a=(168, 202, 232), mtn_b=(188, 218, 248),
        cloud_col=(218, 232, 255), glow=None,
        gravity=1.0, friction=0.25, amp=160, freq=0.010, mood="day",
    ),
    dict(
        name="DEEP_SEA", label="深海",
        sky_a=(4, 16, 52), sky_b=(10, 45, 108),
        g0=(16, 62, 102), g1=(9, 40, 75), g2=(5, 24, 50),
        mtn_a=(10, 45, 82), mtn_b=(16, 60, 105),
        cloud_col=(50, 120, 200), glow=(80, 200, 255),
        gravity=0.45, friction=0.85, amp=118, freq=0.011, mood="deep",
    ),
    dict(
        name="MOON", label="月面",
        sky_a=(3, 3, 13), sky_b=(17, 13, 38),
        g0=(148, 148, 158), g1=(102, 102, 112), g2=(48, 48, 58),
        mtn_a=(82, 82, 92), mtn_b=(102, 102, 112),
        cloud_col=(255, 255, 255), glow=(238, 228, 205),
        gravity=0.17, friction=0.8, amp=125, freq=0.009, mood="night",
    ),
    dict(
        name="NEON", label="霓虹都市",
        sky_a=(7, 3, 20), sky_b=(16, 6, 40),
        g0=(30, 22, 52), g1=(20, 14, 38), g2=(12, 8, 26),
        mtn_a=(16, 10, 35), mtn_b=(24, 16, 50),
        cloud_col=(200, 80, 255), glow=(0, 220, 255),
        gravity=1.0, friction=0.88, amp=78, freq=0.012, mood="neon",
    ),
    dict(
        name="VOLCANO", label="熔岩",
        sky_a=(28, 5, 3), sky_b=(85, 19, 9),
        g0=(58, 17, 13), g1=(38, 11, 8), g2=(18, 5, 3),
        mtn_a=(45, 13, 7), mtn_b=(62, 17, 11),
        cloud_col=(145, 65, 28), glow=(255, 75, 15),
        gravity=1.0, friction=1.0, amp=195, freq=0.015, mood="hell",
    ),
    dict(
        name="CANDY", label="糖果星球",
        sky_a=(255, 145, 195), sky_b=(195, 165, 255),
        g0=(255, 155, 205), g1=(228, 125, 180), g2=(198, 95, 155),
        mtn_a=(255, 175, 220), mtn_b=(215, 155, 255),
        cloud_col=(255, 235, 255), glow=(255, 195, 255),
        gravity=0.68, friction=0.88, amp=168, freq=0.012, mood="candy",
    ),
]
BIOME_LEN = 500

GAME_SEED = 0  # 每次 _reset() 时更新

def slot_biome_idx(slot):
    """每个500m槽位独立随机选场景，由 GAME_SEED 保证本局一致。"""
    if slot == 0:
        # 第一关：保证正常重力，不从低重力场景开局
        normal = [i for i, b in enumerate(BIOMES)
                  if b["gravity"] >= 0.9 and b["name"] != "NEON"]
        return random.Random(GAME_SEED).choice(normal)
    return random.Random(GAME_SEED + slot * 1_000_003).randint(0, len(BIOMES) - 1)

def get_biome_blend(x):
    """只在场景末尾的 18% 向下一个场景渐变。
    每个槽位独立随机（由 GAME_SEED 保证本局内一致）。"""
    slot = max(0, int(x / BIOME_LEN))
    pos  = x % BIOME_LEN if x > 0 else 0.0
    zone = BIOME_LEN * 0.18
    b0   = BIOMES[slot_biome_idx(slot)]
    if x <= 0:
        return b0, b0, 0.0
    if pos > BIOME_LEN - zone:
        t  = (pos - (BIOME_LEN - zone)) / zone
        b1 = BIOMES[slot_biome_idx(slot + 1)]
        return b0, b1, t
    return b0, b0, 0.0

# ════════════════════════════ 精灵系统 ════════════════════════════
SPRITES: dict = {}          # 原始图像
SPRITE_S: dict = {}         # 预缩放缓存
_CLOUD_CACHE: dict = {}     # 云朵尺寸缓存

def load_sprites():
    """在 pygame.init() 后调用，加载 game/assets/sprites/ 下所有 PNG"""
    global SPRITES, SPRITE_S
    base = _resource_dir()
    dirs = [base / "game" / "assets" / "sprites",
            base / "assets" / "sprites"]
    sprite_dir = next((d for d in dirs if d.exists()), None)
    if sprite_dir is None:
        return
    for f in sprite_dir.glob("*.png"):
        try:
            img = pygame.image.load(str(f)).convert_alpha()
            SPRITES[f.stem] = img
        except Exception:
            pass
    # 预缩放到游戏里用到的尺寸（像素）
    sizes = {
        "bush":         (58,  58),
        "plant":        (48,  52),
        "plant_purple": (48,  52),
        "cactus":       (48,  68),
        "rock":         (42,  42),
        "snowhill":     (72,  46),
        "pine":         (46,  70),
        "snowball":     (50,  50),
        "lollipop_red":   (34, 66),
        "lollipop_green": (34, 66),
        "cane_pink":      (28, 72),
        "cupcake":        (36, 36),
        "heart":          (28, 28),
        "cherry":         (30, 36),
        # 深海
        "seaweed_a":  (24, 44), "seaweed_b":  (22, 42),
        "seaweed_c":  (20, 38), "seaweed_d":  (22, 40),
        "bubble_a":   (22, 22), "bubble_b":   (18, 18),
        "fish_blue":  (58, 36), "fish_orange":(58, 36), "fish_pink":(52, 32),
        "sea_rock_a": (48, 40), "sea_rock_b": (42, 36),
        # 月面
        "moon_rock":  (44, 38),
        # 霓虹都市
    }
    for name, (w, h) in sizes.items():
        if name in SPRITES:
            SPRITE_S[name] = pygame.transform.scale(SPRITES[name], (w, h))

def get_cloud_sprite(name, target_w):
    """按需缓存不同宽度的云朵精灵"""
    # 量化到最近的 40 倍数，减少缓存条目
    qw = max(80, round(target_w / 40) * 40)
    key = (name, qw)
    if key not in _CLOUD_CACHE:
        base = SPRITES.get(name)
        if base is None:
            _CLOUD_CACHE[key] = None
            return None
        ratio = qw / base.get_width()
        qh    = max(1, int(base.get_height() * ratio))
        _CLOUD_CACHE[key] = pygame.transform.scale(base, (qw, qh))
    return _CLOUD_CACHE[key]

def blit_sprite(surf, name, sx, sy, alpha=255):
    """将预缩放精灵以底部中心对齐绘制到 (sx, sy)"""
    img = SPRITE_S.get(name)
    if img is None:
        return False
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    w, h = img.get_size()
    surf.blit(img, (sx - w // 2, sy - h))
    return True


CARS = [
    dict(key="touring", label="云游",
         body=(245, 230, 185), roof=(210, 195, 150),
         accent=(140, 110, 65), glass=(180, 225, 245),
         mass=420, engine=1300, width=2.4, height=1.05,
         max_speed_kmh=120,   # 限速 120 km/h
         tilt_mult=0.20,      # 极难倾翻
         inertia_mult=2.8,    # 高惯性，超稳
         desc="限速120·稳如泰山·看风景专用"),
    dict(key="racer", label="逐风",
         body=(62, 135, 210), roof=(45, 105, 175),
         accent=(255, 225, 38), glass=(148, 200, 225),
         mass=230, engine=2600, width=2.0, height=0.60,
         max_speed_kmh=240,   # 限速 240 km/h
         tilt_mult=1.0,       # 正常手感
         inertia_mult=1.0,
         desc="限速240·追风而驰·正常驾驶"),
    dict(key="rocket", label="离弦",
         body=(255, 65, 40), roof=(220, 45, 25),
         accent=(255, 240, 0), glass=(148, 200, 225),
         mass=110, engine=5500, width=1.5, height=1.10,
         max_speed_kmh=9999,  # 无限速
         tilt_mult=4.5,       # 疯狂旋转
         inertia_mult=0.12,   # 极低惯性，随时起飞
         desc="不限速·一触即飞·神经病专用"),
]

# ════════════════════════════ 音乐文件夹 ════════════════════════════
MUSIC_DIR = _user_data_dir() / "Music"

def scan_music_files():
    """扫描 Music/ 文件夹下的音频文件，返回路径列表"""
    MUSIC_DIR.mkdir(exist_ok=True)
    files = []
    for ext in ("*.mp3", "*.ogg", "*.wav"):
        files.extend(MUSIC_DIR.glob(ext))
    return sorted(files)


# ════════════════════════════ 节拍分析 ════════════════════════════
def _detect_beats_from_samples(samp, sr):
    """智能自适应节拍检测：输入单声道float32 numpy数组，返回 (beat_times, bpm)。

    核心思路：
    1. 提取 onset（突然变响的瞬间） + 用自相关找 BPM
    2. 用 onset 统计特征判断音乐类型（强对比/弱对比/中等）
    3. 目标驱动密度：尝试 4 组参数，选最接近"理想节拍密度"的
       （理想密度 = BPM/60 拍/秒，但裁剪到 0.8~2.5 区间避免极端）
    """
    import numpy as np
    if len(samp) < sr * 2:
        return [], 120.0
    # 1. 简单一阶高通：差分 → 强化鼓点/重音的瞬态
    samp_hp = np.diff(samp, prepend=samp[0])
    # 2. 短时能量包络（30ms 窗，10ms 步）
    win = max(1, int(sr * 0.030))
    hop = max(1, int(sr * 0.010))
    n_frames = (len(samp_hp) - win) // hop
    if n_frames < 10:
        return [], 120.0
    env = np.array([
        np.sqrt(np.mean(samp_hp[i*hop : i*hop+win] ** 2) + 1e-12)
        for i in range(n_frames)
    ])
    # 3. Onset = 包络的正向差分
    onset = np.maximum(0.0, np.diff(env, prepend=env[0]))
    if onset.max() > 0:
        onset = onset / onset.max()
    # 4. 自相关找 tempo (60~200 BPM)
    fps_onset = sr / hop
    lag_min   = max(2, int(fps_onset * 60.0 / 200.0))
    lag_max   = min(len(onset) - 1, int(fps_onset * 60.0 / 60.0))
    if lag_max <= lag_min:
        bpm = 120.0
    else:
        ac = np.array([
            np.sum(onset[:len(onset)-lag] * onset[lag:])
            for lag in range(lag_min, lag_max)
        ])
        best_lag = lag_min + int(np.argmax(ac))
        bpm = 60.0 * fps_onset / best_lag
        bpm = max(60.0, min(200.0, bpm))
    # 5. onset 统计特征：判断"节奏感强弱"
    pos_onset = onset[onset > 0.02]
    if len(pos_onset) > 10:
        onset_ratio = float(pos_onset.std() / (pos_onset.mean() + 1e-6))
    else:
        onset_ratio = 1.0
    # 6. 根据统计特征选起始参数（thr_mult, gap_mult）
    #    onset_ratio 高 → 节拍清晰 → 用较严阈值；低 → 用宽松阈值但拉大最小间隔
    if onset_ratio > 1.6:
        # 强对比：电音/EDM — 阈值高，只取真正强的鼓点
        candidates = [(3.5, 0.80), (3.0, 0.75), (4.0, 0.85), (2.5, 0.90)]
    elif onset_ratio < 0.9:
        # 弱对比：人声/民谣/古典 — 间隔大，避免人声爆破被误检
        candidates = [(2.5, 1.20), (2.0, 1.30), (3.0, 1.10), (3.5, 1.00)]
    else:
        # 中等：流行
        candidates = [(3.0, 0.95), (2.5, 1.00), (3.5, 0.90), (4.0, 0.85)]
    # 7. 多组参数挑峰，选密度最接近"目标"的一组
    beat_interval_frames = int(fps_onset * 60.0 / bpm)
    ctx_frames = int(fps_onset * 2.0)
    duration_s = n_frames * hop / sr
    # 目标节拍密度：每 2 拍一个菱形，裁剪到 [0.4, 1.0] 拍/秒
    # （120BPM → 1.0/秒，180BPM → 1.0/秒上限，慢歌 60BPM → 0.5/秒）
    target_density = max(0.4, min(1.0, bpm / 60.0 / 2.0))
    def _pick_peaks(thr_mult, gap_mult):
        min_gap = max(1, int(beat_interval_frames * gap_mult))
        out = []
        for i in range(1, len(onset) - 1):
            lo = max(0, i - ctx_frames)
            hi = min(len(onset), i + ctx_frames)
            thr = onset[lo:hi].mean() * thr_mult
            if (onset[i] > thr
                    and onset[i] >= onset[i-1]
                    and onset[i] >= onset[i+1]):
                if not out or i - out[-1] >= min_gap:
                    out.append(i)
        return out
    best_peaks   = None
    best_score   = float("inf")
    for thr_mult, gap_mult in candidates:
        pk = _pick_peaks(thr_mult, gap_mult)
        density = len(pk) / max(1.0, duration_s)
        # 评分 = |实际密度 - 目标密度|，越小越好
        score = abs(density - target_density)
        if score < best_score:
            best_score = score
            best_peaks = pk
    peaks = best_peaks if best_peaks is not None else []
    beat_times = [p * hop / sr for p in peaks]
    return beat_times, float(bpm)


# ── 节拍缓存：避免每次切歌都重新分析（耗 1-2 秒）──
def _beat_cache_load():
    if not BEAT_CACHE_PATH.exists():
        return {}
    try:
        with open(BEAT_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _beat_cache_save(cache):
    try:
        with open(BEAT_CACHE_PATH, "w", encoding="utf-8") as f:
            # 节拍数组太长，不缩进省空间
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def analyze_music_beats(filepath):
    """带缓存的节拍分析。命中缓存 < 50ms，未命中正常分析后写入缓存。
    返回 (beat_times列表, bpm, 时长秒)。"""
    # 缓存键 = 绝对路径；失效条件 = 文件修改时间变了
    try:
        mtime = os.path.getmtime(filepath)
        key   = str(Path(filepath).resolve())
    except Exception:
        mtime = 0.0
        key   = filepath
    cache = _beat_cache_load()
    entry = cache.get(key)
    if entry and abs(entry.get("mtime", -1) - mtime) < 0.5:
        # 缓存命中
        return (entry.get("beats", []),
                float(entry.get("bpm", 120.0)),
                float(entry.get("duration", 180.0)))
    # 未命中：调用真分析函数
    beats, bpm, dur = _analyze_music_beats_uncached(filepath)
    # 写入缓存
    cache[key] = {
        "mtime":    mtime,
        "bpm":      float(bpm),
        "duration": float(dur),
        "beats":    [round(b, 3) for b in beats],   # 保留 3 位小数省空间
    }
    _beat_cache_save(cache)
    return beats, bpm, dur


def _analyze_music_beats_uncached(filepath):
    """实际做节拍分析的函数（耗时 1-2 秒）。
    多重 fallback：高级算法 → pygame解码 → 等距生成。"""
    import numpy as np
    fname = filepath.lower()
    # ── 路径1：WAV 用 wave 模块直接解码 ─────────────────────────
    if fname.endswith('.wav'):
        try:
            import wave
            with wave.open(filepath, 'rb') as wf:
                sr  = wf.getframerate()
                nch = wf.getnchannels()
                raw = wf.readframes(wf.getnframes())
            samp = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            if nch > 1:
                samp = samp.reshape(-1, nch).mean(1)
            duration   = len(samp) / sr
            beats, bpm = _detect_beats_from_samples(samp, sr)
            if len(beats) >= 8:
                return beats, bpm, float(duration)
        except Exception:
            pass
    # ── 路径2：MP3/OGG 用 pygame.sndarray 解码 ──────────────────
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init(44100, -16, 2, 128)
        snd  = pygame.mixer.Sound(filepath)
        arr  = pygame.sndarray.array(snd).astype(np.float32) / 32768.0
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        sr   = pygame.mixer.get_init()[0]
        duration   = len(arr) / sr
        beats, bpm = _detect_beats_from_samples(arr, sr)
        if len(beats) >= 8:
            return beats, bpm, float(duration)
        # 如果解码成功但节拍检出失败，至少用真实时长 + 120BPM
        return ([i * 0.5 for i in range(int(duration * 2))],
                120.0, float(duration))
    except Exception:
        pass
    # ── 路径3：最终回退 - 文件大小估算 + 120BPM ────────────────
    try:
        fsize    = os.path.getsize(filepath)
        duration = max(30.0, fsize / 20000.0)
        bpm      = 120.0
        beats    = [i * 60.0 / bpm for i in range(int(duration * bpm / 60))]
        return beats, bpm, duration
    except Exception:
        return [], 120.0, 180.0


# ════════════════════════════ 坐标转换 ════════════════════════════
def scr(wx, wy, cam):
    return (int(wx * PPM - cam.x + W * 0.35),
            int(H * 0.65 - (wy * PPM - cam.y)))


# ════════════════════════════ 地形 ════════════════════════════════
class Terrain:
    def __init__(self, seed=None):
        rng = random.Random(seed)
        self.layers = [
            (0.008, 1.00, rng.uniform(0, math.tau)),
            (0.022, 0.45, rng.uniform(0, math.tau)),
            (0.055, 0.18, rng.uniform(0, math.tau)),
            (0.12,  0.07, rng.uniform(0, math.tau)),
        ]
        self.warmup = 60.0

    def biome(self, x):
        return BIOMES[slot_biome_idx(max(0, int(x / BIOME_LEN)))]

    def bidx(self, x):
        return slot_biome_idx(max(0, int(x / BIOME_LEN)))

    def height(self, x):
        ease   = min(1.0, (max(0.0, x) / self.warmup) ** 2) if x < self.warmup else 1.0
        b0, b1, t = get_biome_blend(x)
        amp    = lerp(b0["amp"], b1["amp"], t) / PPM
        y      = sum(math.sin(x * f + ph) * amp * a for f, a, ph in self.layers) * ease
        return y

    def slope(self, x, dx=0.4):
        return (self.height(x + dx) - self.height(x - dx)) / (2 * dx)

    def normal(self, x):
        s = self.slope(x)
        n = pygame.Vector2(-s, 1.0)
        l = n.length()
        return n / l if l > 1e-9 else pygame.Vector2(0, 1)

    def collide_circle(self, cx, cy, r):
        gy = self.height(cx)
        n  = self.normal(cx)
        d  = (cy - gy) * n.y
        return (d < r, n, max(0.0, r - d))


# ════════════════════════════ 视差背景 ════════════════════════════
class ParallaxBG:
    """多层视差背景：远山 / 近山 / 云 / 月面星星"""

    def __init__(self, seed=0):
        rng = random.Random(seed + 999)
        self.clouds = []
        for _ in range(22):
            self.clouds.append({
                "wx":    rng.uniform(-60, 700),
                "wy":    rng.uniform(0.52, 0.78),
                "w":     rng.randint(75, 195),
                "h":     rng.randint(20, 44),
                "sp":    rng.uniform(0.018, 0.052),
                "pf":    rng.uniform(0.07, 0.17),
                "alpha": rng.randint(135, 215),
            })
        self.stars = [
            (rng.randint(0, W), rng.randint(0, int(H * 0.72)),
             rng.randint(1, 2), rng.uniform(0.4, 1.0))
            for _ in range(200)
        ]
        self._mtn: dict[int, list] = {}
        self.t = 0.0

    def step(self, dt):
        self.t += dt
        for c in self.clouds:
            c["wx"] -= c["sp"] * dt * 60
            if c["wx"] * PPM + c["w"] < -200 + self.t * 0:
                c["wx"] = W / PPM + random.uniform(5, 45)
                c["wy"] = random.uniform(0.52, 0.80)

    def _mtn_pts(self, chunk_id, layer):
        key = (chunk_id, layer)
        if key not in self._mtn:
            rng  = random.Random(chunk_id * 137 + layer * 53 + 42)
            n    = 22
            pts  = []
            for i in range(n):
                x = chunk_id * W + i * (W // (n - 1))
                h = rng.uniform(0.28 + layer * 0.12, 0.52 + layer * 0.10)
                pts.append((x, h))
            self._mtn[key] = pts
        return self._mtn[key]

    def draw(self, surf, cam, car_x):
        b0, b1, bt = get_biome_blend(car_x)
        # 混合颜色
        sky_a     = lerpC(b0["sky_a"],    b1["sky_a"],    bt)
        sky_b     = lerpC(b0["sky_b"],    b1["sky_b"],    bt)
        mtn_a     = lerpC(b0["mtn_a"],    b1["mtn_a"],    bt)
        mtn_b     = lerpC(b0["mtn_b"],    b1["mtn_b"],    bt)
        cloud_col = lerpC(b0["cloud_col"],b1["cloud_col"],bt)
        mood      = b0["mood"] if bt < 0.5 else b1["mood"]

        # ── 渐变天空（颜色跨场景混合）
        for y in range(0, H, 3):
            pygame.draw.rect(surf, lerpC(sky_a, sky_b, y / H), (0, y, W, 3))

        # ── 场景特效
        if mood == "night":
            pygame.draw.circle(surf, (238, 230, 205), (W - 155, 82), 50)
            pygame.draw.circle(surf, (218, 210, 185), (W - 140, 72), 11)
            pygame.draw.circle(surf, (218, 210, 185), (W - 162, 92), 8)
            for sx, sy, r, br in self.stars:
                tw = (math.sin(self.t * 1.8 + sx * 0.1) * 0.3 + 0.7) * br
                col = lerpC((35, 30, 72), (255, 255, 240), tw)
                pygame.draw.circle(surf, col, (sx, sy), r)

        elif mood == "hell":
            pygame.draw.circle(surf, (155, 38, 12), (155, 92), 56)
            pygame.draw.circle(surf, (198, 58, 18), (155, 92), 43)
            pygame.draw.circle(surf, (238, 88, 28), (155, 92), 29)
            for k in range(8):
                ang = k * math.pi / 4 + self.t * 0.65
                rr  = 67 + math.sin(self.t * 2.1 + k) * 9
                ex  = 155 + math.cos(ang) * rr
                ey  = 92  + math.sin(ang) * rr
                pygame.draw.circle(surf, (175, 48, 14), (int(ex), int(ey)), 7)

        elif mood == "desert":
            # 巨大烈日
            pygame.draw.circle(surf, (255, 230, 100), (W - 130, 70), 48)
            pygame.draw.circle(surf, (255, 248, 180), (W - 130, 70), 32)
            # 太阳光芒
            for k in range(10):
                ang = k * math.pi / 5 + self.t * 0.25
                x1  = W - 130 + math.cos(ang) * 52
                y1  = 70      + math.sin(ang) * 52
                x2  = W - 130 + math.cos(ang) * 70
                y2  = 70      + math.sin(ang) * 70
                pygame.draw.line(surf, (255, 220, 80), (int(x1),int(y1)), (int(x2),int(y2)), 2)

        elif mood == "deep":
            # 海底幽光：随机发光点
            rng_d = random.Random(int(self.t * 3))
            for _ in range(12):
                gx = rng_d.randint(0, W)
                gy = rng_d.randint(int(H * 0.3), H)
                gr = rng_d.randint(3, 8)
                ga = rng_d.randint(30, 80)
                gs = pygame.Surface((gr*2, gr*2), pygame.SRCALPHA)
                pygame.draw.circle(gs, (80, 200, 255, ga), (gr, gr), gr)
                surf.blit(gs, (gx - gr, gy - gr))

        elif mood == "neon":
            # 霓虹都市：建筑剪影
            rng_n = random.Random(42)
            off_n = int(cam.x * 0.35) % W
            for i in range(14):
                bx = (i * 95 - off_n) % (W + 100) - 50
                bh = rng_n.randint(80, 280)
                bw = rng_n.randint(45, 90)
                col_b = (18, 12, 40)
                pygame.draw.rect(surf, col_b, (bx, H - bh, bw, bh))
                # 霓虹窗户
                rng_w = random.Random(i * 31 + int(self.t * 0.5))
                neon_cols = [(0,220,255),(255,50,200),(80,255,120),(255,200,50)]
                for wy_ in range(H - bh + 8, H - 20, 20):
                    for wx_ in range(bx + 6, bx + bw - 6, 14):
                        if rng_w.random() < 0.55:
                            wc = rng_w.choice(neon_cols)
                            ws = pygame.Surface((8, 10), pygame.SRCALPHA)
                            ws.fill((*wc, 180))
                            surf.blit(ws, (wx_, wy_))
            # 雨条
            rng_r = random.Random(int(self.t * 25))
            ov_r  = pygame.Surface((W, H), pygame.SRCALPHA)
            for _ in range(40):
                rx = rng_r.randint(0, W)
                ry = rng_r.randint(0, H)
                pygame.draw.line(ov_r, (120, 180, 255, 55),
                                 (rx, ry), (rx - 1, ry + 14), 1)
            surf.blit(ov_r, (0, 0))

        elif mood == "candy":
            # 彩虹条纹天空覆盖
            rainbow = [(255,100,150),(255,180,80),(255,240,80),
                       (120,240,120),(80,190,255),(180,100,255)]
            ov_c = pygame.Surface((W, H), pygame.SRCALPHA)
            for i, rc in enumerate(rainbow):
                y0 = int(i * H / len(rainbow) * 0.75)
                y1 = int((i+1) * H / len(rainbow) * 0.75)
                pygame.draw.rect(ov_c, (*rc, 35), (0, y0, W, y1 - y0))
            surf.blit(ov_c, (0, 0))
            # 漂浮爱心/星星
            rng_k = random.Random(int(self.t * 2))
            for _ in range(8):
                kx = rng_k.randint(0, W)
                ky = rng_k.randint(20, int(H * 0.6))
                kc = rng_k.choice([(255,100,180),(255,220,80),(180,100,255)])
                pygame.draw.circle(surf, kc, (kx, ky), rng_k.randint(3, 7))

        # ── 远景山脉 (视差 0.055)
        pf0  = 0.055
        off0 = cam.x * pf0
        c0   = int(off0 / W) - 1
        for cid in range(c0, c0 + 3):
            pts  = self._mtn_pts(cid, 0)
            poly = [(int(x - off0), int(H * p)) for x, p in pts]
            if len(poly) >= 2:
                full = poly + [(poly[-1][0], H + 10), (poly[0][0], H + 10)]
                pygame.draw.polygon(surf, mtn_a, full)

        # ── 近景山脉 (视差 0.16)
        pf1  = 0.16
        off1 = cam.x * pf1
        c1   = int(off1 / W) - 1
        for cid in range(c1, c1 + 3):
            pts  = self._mtn_pts(cid, 1)
            poly = [(int(x - off1), int(H * p)) for x, p in pts]
            if len(poly) >= 2:
                full = poly + [(poly[-1][0], H + 10), (poly[0][0], H + 10)]
                pygame.draw.polygon(surf, mtn_b, full)

        # ── 云朵（优先使用 Kenney 精灵，降级为程序绘制）
        _cloud_names = ["cloud1", "cloud2", "cloud3"]
        for ci, c in enumerate(self.clouds):
            sx  = int(c["wx"] * PPM - cam.x * c["pf"] + W * 0.35)
            sy  = int(c["wy"] * H)
            cw, ch_ = c["w"], c["h"]
            alpha   = c["alpha"]
            if mood in ("night", "deep", "neon"):
                alpha = min(alpha, 28)
            if alpha < 18:
                continue
            cname = _cloud_names[ci % 3]
            cimg  = get_cloud_sprite(cname, cw)
            if cimg is not None:
                # 用场景颜色着色：复制 + BLEND_MULT
                tinted = cimg.copy()
                tinted.set_alpha(alpha)
                # 轻微染色：与 cloud_col 混合
                tint_s = pygame.Surface(cimg.get_size(), pygame.SRCALPHA)
                tint_s.fill((*cloud_col, 160))
                tinted.blit(tint_s, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(tinted, (sx - cimg.get_width() // 2,
                                   sy - cimg.get_height()))
            else:
                # 程序降级
                cs = pygame.Surface((cw + ch_, ch_ * 2), pygame.SRCALPHA)
                pygame.draw.ellipse(cs, (*cloud_col, alpha),
                                    (ch_ // 2, ch_ // 2, cw, ch_))
                surf.blit(cs, (sx - ch_ // 2, sy - ch_))

        # ── 场景特效（带淡入淡出）
        _slot = int(car_x / BIOME_LEN)
        _pos  = car_x % BIOME_LEN
        a0 = int(255 * (1.0 - bt))
        a1 = int(255 * bt)
        if a0 > 8:
            self._biome_fx(surf, cam, b0, a0, _slot, _pos)
        if a1 > 8 and b1["name"] != b0["name"]:
            self._biome_fx(surf, cam, b1, a1, _slot + 1, 0)

    def _biome_fx(self, surf, cam, b, alpha, slot, pos_in_slot):
        """每个场景的特色背景元素。
        大型元素（金字塔/极光/彩虹）：每槽随机在80~300m处出现一次，渐入渐出。
        小型元素（气泡/流星/飞行器/火球）：时间驱动，循环出现但不过密。
        alpha：场景切换时的整体透明度（由 bt 控制）。
        """
        t    = self.t
        name = b["name"]
        ov   = pygame.Surface((W, H), pygame.SRCALPHA)

        # ── 大型元素：随机时机出现，渐入渐出
        rng_L      = random.Random(GAME_SEED + slot * 88881 + abs(hash(name)) % 9999)
        appear_at  = rng_L.uniform(80, 300)
        vanish_at  = BIOME_LEN * 0.84
        fade_d     = 55
        if pos_in_slot < appear_at or pos_in_slot >= vanish_at:
            large_a = 0
        elif pos_in_slot - appear_at < fade_d:
            large_a = int(alpha * (pos_in_slot - appear_at) / fade_d)
        elif vanish_at - pos_in_slot < fade_d:
            large_a = int(alpha * (vanish_at - pos_in_slot) / fade_d)
        else:
            large_a = alpha

        # 大型元素的世界坐标（低视差定位）
        pf_large  = 0.055
        elem_wx   = slot * BIOME_LEN + rng_L.uniform(BIOME_LEN * 0.2, BIOME_LEN * 0.65)
        sx_center = int(elem_wx * PPM * pf_large - cam.x * pf_large + W * 0.35)

        if name == "DESERT" and large_a > 4:
            # 金字塔组：以 sx_center 为主体
            rng_p = random.Random(slot * 2231 + 13)
            sizes = [(200, 160), (140, 110), (100, 80)]
            offsets = [0, rng_p.randint(120, 180), rng_p.randint(-160, -100)]
            by = int(H * 0.63)
            for (pw, ph), ox in zip(sizes, offsets):
                bx = sx_center + ox - pw // 2
                col_p = (175, 138, 72, large_a)
                pygame.draw.polygon(ov, col_p,
                                    [(bx, by), (bx + pw // 2, by - ph), (bx + pw, by)])
                pygame.draw.polygon(ov, (140, 108, 52, large_a),
                                    [(bx + pw // 2, by - ph),
                                     (bx + pw, by), (bx + pw * 3 // 4, by)])
            # 海市蜃楼（只在出现期间）
            mir_a = int(large_a * 0.40)
            for row in range(3):
                y_m = int(H * 0.60) + row * 5
                for x_m in range(0, W, 6):
                    wave = math.sin(x_m * 0.04 + t * 1.2 + row) * 2
                    pygame.draw.rect(ov, (200, 180, 120, mir_a),
                                     (x_m, int(y_m + wave), 4, 2))

        elif name == "ICE" and large_a > 4:
            # 极光：竖向光柱，从天空垂挂，横向流动
            aurora_cols = [
                (55,  255, 130),   # 主绿
                (40,  195, 255),   # 青蓝
                (165, 75,  255),   # 紫
            ]
            bar_w = 8
            for ci, col_a in enumerate(aurora_cols):
                pc = ci * 2.3
                for bx in range(0, W + bar_w, bar_w):
                    # 多频叠加 → 光柱强度
                    nx = (math.sin(bx * 0.009 + t * 0.28 + pc) * 0.50 +
                          math.sin(bx * 0.026 + t * 0.52 + pc) * 0.32 +
                          math.sin(bx * 0.072 + t * 0.85 + pc) * 0.18)
                    intensity = max(0.0, nx)
                    if intensity < 0.10:
                        continue
                    ray_h = int(intensity * 185)
                    y_top = int(H * 0.04 + ci * 18)
                    # 竖向 5 层渐变（sin 曲线：中间最亮，两端淡出）
                    for layer in range(6):
                        lt     = layer / 5
                        bright = math.sin(lt * math.pi)
                        a_px   = int(bright * intensity * 90 * large_a / 255)
                        if a_px < 3:
                            continue
                        y_px = y_top + int(lt * ray_h)
                        h_px = max(2, ray_h // 5 + 1)
                        pygame.draw.rect(ov, (*col_a, a_px),
                                         (bx, y_px, bar_w, h_px))

        elif name == "CANDY" and large_a > 4:
            # 彩虹（全屏弧，以 sx_center 偏移位置）
            rainbow_cols = [(255,50,50),(255,160,30),(255,230,30),
                            (80,220,60),(50,160,255),(130,60,255)]
            cx_r = sx_center
            cy_r = int(H * 0.72)
            for ri, rc in enumerate(rainbow_cols):
                r_o = 200 + ri * 22
                try:
                    pygame.draw.arc(ov, (*rc, int(large_a * 0.60)),
                                    (cx_r - r_o, cy_r - r_o // 2, r_o * 2, r_o),
                                    0, math.pi, 14)
                except Exception:
                    pass

        # ── 小型循环元素（时间驱动，不依赖出现时机）
        if name == "DEEP_SEA":
            # 气泡：3层，每层5个，周期性上浮
            for layer in range(3):
                period_b = 8.0 + layer * 3.5
                rng_b    = random.Random(layer * 777 + int(t / period_b))
                phase_b  = (t % period_b) / period_b
                for j in range(5):
                    bx = rng_b.randint(0, W)
                    by = int(H * 0.88 - phase_b * H * 0.75 - j * (H * 0.75 / 5))
                    r  = rng_b.randint(2 + layer, 4 + layer * 2)
                    ba = int(alpha * rng_b.uniform(0.20, 0.45))
                    if 0 < by < H:
                        pygame.draw.circle(ov, (130, 200, 255, ba), (bx % W, by), r, 1)

        elif name == "MOON":
            # 流星：随机大小（粗细/长度/亮度各异）
            for k in range(2):
                period  = 5.5 + k * 3.2
                phase_t = (t + k * period * 0.55) % period
                if phase_t < 0.9:
                    prog  = phase_t / 0.9
                    rng_m = random.Random(int((t + k * period * 0.55) / period) * 200 + k)
                    sx0    = rng_m.randint(W // 3, W - 60)
                    sy0    = rng_m.randint(20, int(H * 0.32))
                    length = rng_m.randint(60, 200)       # 长短随机
                    head_r = rng_m.uniform(1.2, 3.8)      # 头部大小随机
                    bright = rng_m.uniform(0.7, 1.0)      # 亮度随机
                    trail_segs = rng_m.randint(5, 10)     # 尾迹节数随机
                    for seg in range(trail_segs):
                        seg_t = seg / trail_segs
                        sa = int(alpha * bright * (1 - seg_t) * (1 - prog * 0.65))
                        px = int(sx0 - length * prog * (1 - seg_t * 0.4))
                        py = int(sy0 + length * 0.4 * prog * (1 - seg_t * 0.4))
                        r  = max(1, int(head_r * (1 - seg_t)))
                        pygame.draw.circle(ov, (255, 255, 220, sa), (px, py), r)

        elif name == "NEON":
            # 飞行器：同一时刻1~2架，周期6~10s
            for k in range(2):
                period_n = 7.0 + k * 3.0
                phase_n  = (t + k * period_n * 0.5) % period_n
                prog_n   = phase_n / period_n
                fx       = int(prog_n * (W + 80)) - 40
                fy       = int(H * (0.14 + k * 0.10))
                col_n    = [(0, 220, 255), (255, 50, 200)][k]
                fa       = int(alpha * 0.82)
                body_pts = [(fx, fy), (fx + 22, fy - 5), (fx + 30, fy), (fx + 22, fy + 5)]
                pygame.draw.polygon(ov, (20, 20, 35, fa), body_pts)
                pygame.draw.polygon(ov, (*col_n, fa), body_pts, 1)
                pygame.draw.circle(ov, (*col_n, fa), (fx - 2, fy), 3)
                for tr in range(7):
                    ta = int(fa * (1 - tr / 7) * 0.45)
                    pygame.draw.circle(ov, (*col_n, ta), (fx - tr * 5, fy), max(1, 2 - tr // 3))

        elif name == "VOLCANO":
            # 火球：随机大小（小碎石~大火球）
            for k in range(2):
                period_f = 4.5 + k * 2.5
                phase_f  = (t + k * period_f * 0.6) % period_f
                if phase_f < 1.6:
                    prog_f  = phase_f / 1.6
                    rng_f   = random.Random(int((t + k * period_f * 0.6) / period_f) * 55 + k)
                    sx_f    = rng_f.randint(60, W - 60)
                    r_f     = rng_f.randint(3, 12)        # 大小随机：3=碎石 12=大火球
                    speed_f = rng_f.uniform(0.40, 0.65)   # 下落速度随机
                    angle_f = rng_f.uniform(-0.15, 0.15)  # 轻微偏斜
                    fy_f    = int(H * 0.04 + H * speed_f * prog_f)
                    fx_f    = int(sx_f + H * angle_f * prog_f)
                    fa_f    = int(alpha * (1 - prog_f * 0.40))
                    # 外焰（大球才有）
                    if r_f >= 6:
                        pygame.draw.circle(ov, (255, 80, 10, int(fa_f * 0.5)),
                                           (fx_f, fy_f), r_f + 3)
                    pygame.draw.circle(ov, (255, 130 + r_f * 5, 20, fa_f), (fx_f, fy_f), r_f)
                    pygame.draw.circle(ov, (255, 220, 80, fa_f), (fx_f, fy_f), max(1, r_f - 2))
                    # 尾迹长度跟大小成正比
                    tail_len = int(r_f * 0.85)
                    for tr in range(tail_len):
                        ta = int(fa_f * (1 - tr / tail_len) * 0.55)
                        ty = fy_f - tr * (5 + r_f // 2)
                        tx = fx_f - int(tr * angle_f * 15)
                        pygame.draw.circle(ov, (255, 70, 15, ta), (tx, ty),
                                           max(1, r_f - tr * r_f // tail_len))

        surf.blit(ov, (0, 0))


# ════════════════════════════ 粒子系统 ════════════════════════════
@dataclass
class Particle:
    pos:      pygame.Vector2
    vel:      pygame.Vector2
    life:     float
    max_life: float
    color:    tuple
    size:     float
    gravity:  float = 1.0
    fade:     bool  = True


class Particles:
    def __init__(self):
        self.items: list[Particle] = []

    def emit_dust(self, pos, n=5, color=(155, 138, 108)):
        for _ in range(n):
            self.items.append(Particle(
                pos=pygame.Vector2(pos),
                vel=pygame.Vector2(random.uniform(-2, 2), random.uniform(-0.5, 2.5)),
                life=0.7, max_life=0.7,
                color=color, size=random.uniform(2.5, 5),
                gravity=0.25, fade=True))

    def emit_spark(self, pos, color=(255, 205, 75), n=10):
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            sp  = random.uniform(3, 10)
            self.items.append(Particle(
                pos=pygame.Vector2(pos),
                vel=pygame.Vector2(math.cos(ang) * sp, math.sin(ang) * sp),
                life=random.uniform(0.3, 0.55), max_life=0.55,
                color=color, size=random.uniform(2, 3.5),
                gravity=0.9))

    def emit_debris(self, pos, color, n=6):
        for _ in range(n):
            self.items.append(Particle(
                pos=pygame.Vector2(pos),
                vel=pygame.Vector2(random.uniform(-6, 6), random.uniform(2, 10)),
                life=2.2, max_life=2.2, color=color,
                size=random.uniform(3, 7), gravity=1.6, fade=False))

    def emit_exhaust(self, pos, vel_base, color=(120, 115, 110)):
        for _ in range(2):
            self.items.append(Particle(
                pos=pygame.Vector2(pos),
                vel=pygame.Vector2(vel_base.x * 0.2 + random.uniform(-0.5, 0.5),
                                   vel_base.y * 0.2 + random.uniform(0.5, 1.5)),
                life=0.42, max_life=0.42,
                color=color, size=random.uniform(3, 6),
                gravity=0.1, fade=True))

    def emit_boost(self, pos):
        for _ in range(14):
            ang = random.uniform(math.pi * 0.85, math.pi * 1.15)
            sp  = random.uniform(5, 13)
            col = random.choice([C.BOOST, C.YEL, C.GRN])
            self.items.append(Particle(
                pos=pygame.Vector2(pos),
                vel=pygame.Vector2(math.cos(ang) * sp, math.sin(ang) * sp),
                life=0.55, max_life=0.55,
                color=col, size=random.uniform(3, 5.5),
                gravity=0.4))

    def emit_lava(self, pos):
        for _ in range(18):
            self.items.append(Particle(
                pos=pygame.Vector2(pos),
                vel=pygame.Vector2(random.uniform(-2, 2), random.uniform(7, 15)),
                life=random.uniform(0.7, 1.5), max_life=1.5,
                color=random.choice([(255, 95, 25), (255, 175, 45), (215, 45, 15)]),
                size=random.uniform(4, 8), gravity=2.8))

    def emit_bubble(self, pos):
        """深海上浮气泡"""
        self.items.append(Particle(
            pos=pygame.Vector2(pos),
            vel=pygame.Vector2(random.uniform(-0.3, 0.3), random.uniform(2.0, 4.5)),
            life=random.uniform(1.5, 3.0), max_life=3.0,
            color=(95, 185, 255), size=random.uniform(2.5, 5.5),
            gravity=-0.12, fade=True))

    def emit_skid(self, pos, color=(50, 50, 55)):
        self.items.append(Particle(
            pos=pygame.Vector2(pos),
            vel=pygame.Vector2(random.uniform(-0.5, 0.5), random.uniform(-0.2, 0.5)),
            life=1.2, max_life=1.2,
            color=color, size=random.uniform(2, 4),
            gravity=0.05, fade=True))

    def step(self, dt, grav_scale=1.0):
        keep = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vel.y -= 9.8 * p.gravity * grav_scale * dt
            p.pos   += p.vel * dt
            keep.append(p)
        self.items = keep

    def draw(self, surf, cam):
        for p in self.items:
            t = p.life / p.max_life if p.fade else 1.0
            alpha = max(0, min(255, int(255 * t)))
            sx, sy = scr(p.pos.x, p.pos.y, cam)
            if not (-12 < sx < W + 12 and -12 < sy < H + 12):
                continue
            r = max(1, int(p.size * (0.4 + 0.6 * t)))
            if p.fade:
                s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, (*p.color, alpha), (r, r), r)
                surf.blit(s, (sx - r, sy - r))
            else:
                pygame.draw.circle(surf, p.color, (sx, sy), r)


# ════════════════════════════ 车辆物理 ════════════════════════════
@dataclass
class Wheel:
    pos:      pygame.Vector2
    vel:      pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(0, 0))
    radius:   float  = 0.35
    mass:     float  = 25.0
    spin:     float  = 0.0
    spin_vel: float  = 0.0
    grounded: bool   = False
    detached: bool   = False


@dataclass
class Chassis:
    pos:         pygame.Vector2
    vel:         pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(0, 0))
    angle:       float = 0.0
    angular_vel: float = 0.0
    mass:        float = 280.0
    inertia:     float = 1.0
    width:       float = 1.8
    height:      float = 0.7


@dataclass
class Driver:
    pos:      pygame.Vector2
    vel:      pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(0, 0))
    attached: bool   = True
    radius:   float  = 0.18


class Car:
    REST_LEN     = 0.55
    SPRING_K     = 14000.0
    SPRING_DAMP  = 1400.0
    DRIVER_BREAK = 12.0
    ROOF_BREAK   = 14.0
    WHEEL_BREAK  = 18.0

    def __init__(self, cfg, x=0.0, y=2.0):
        self.cfg = cfg
        w, h = cfg["width"], cfg["height"]
        self.chassis = Chassis(
            pos=pygame.Vector2(x, y), mass=cfg["mass"],
            width=w, height=h,
            inertia=(w * w + h * h) * cfg["mass"] / 12.0 * cfg.get("inertia_mult", 1.0),
        )
        self.wheel_offsets = [
            pygame.Vector2(-w * 0.40, -h * 0.50),
            pygame.Vector2( w * 0.40, -h * 0.50),
        ]
        self.rear  = Wheel(pos=pygame.Vector2(x - w * 0.40, y - h * 0.50 - self.REST_LEN))
        self.front = Wheel(pos=pygame.Vector2(x + w * 0.40, y - h * 0.50 - self.REST_LEN))
        self.driver_offset = pygame.Vector2(-w * 0.15, h * 0.50 + 0.25)
        self.driver = Driver(pos=pygame.Vector2(x - w * 0.15, y + h * 0.50 + 0.25))

        self.alive        = True
        self.roof_on      = True
        self.score_flips  = 0
        self.boost_timer  = 0.0
        self.flip_flash   = 0.0   # 翻滚完成时的屏幕闪光
        self.flip_text_timer = 0.0
        self._angle_acc   = 0.0
        self._last_angle  = 0.0
        self._in_air_time = 0.0
        self._exhaust_t   = 0.0

        self.throttle = 0.0
        self.tilt     = 0.0
        self.brake    = False

    def speed_kmh(self):
        return self.chassis.vel.length() * 3.6

    def step(self, terrain, particles, grav_scale=1.0, fric_scale=1.0):
        if self.boost_timer > 0:
            self.boost_timer = max(0.0, self.boost_timer - DT)
        if self.flip_flash > 0:
            self.flip_flash = max(0.0, self.flip_flash - DT)
        if self.flip_text_timer > 0:
            self.flip_text_timer = max(0.0, self.flip_text_timer - DT)

        for _ in range(SUBSTEPS):
            self._substep(terrain, particles, grav_scale, fric_scale)

        for wh in (self.rear, self.front):
            if wh.detached:
                continue
            if wh.grounded:
                wh.spin_vel = -self.chassis.vel.x / max(0.01, wh.radius)
            wh.spin += wh.spin_vel * DT

        any_ground = self.rear.grounded or self.front.grounded
        if not any_ground:
            self._in_air_time += DT
            da = self.chassis.angle - self._last_angle
            while da >  math.pi: da -= math.tau
            while da < -math.pi: da += math.tau
            self._angle_acc += da
            if abs(self._angle_acc) >= math.tau:
                self.score_flips += 1
                self._angle_acc -= math.copysign(math.tau, self._angle_acc)
                # 翻滚爆发：沿当前速度方向猛推一把
                ch = self.chassis
                spd = ch.vel.length()
                burst = max(22.0, spd * 1.2)
                if abs(ch.vel.x) > 0.1:
                    ch.vel.x += math.copysign(burst, ch.vel.x)
                else:
                    ch.vel.x += burst
                self.flip_flash = 0.55
                self.flip_text_timer = 1.4
                particles.emit_spark(self.chassis.pos, color=C.YEL, n=50)
                particles.emit_spark(self.chassis.pos, color=C.ORG, n=30)
                particles.emit_spark(self.chassis.pos, color=C.PINK, n=15)
        else:
            self._in_air_time = 0.0
            self._angle_acc  *= 0.55
        self._last_angle = self.chassis.angle

        # 自动复位：倒置（角度接近 ±π）且速度很慢时自动扶正
        ch = self.chassis
        norm_a = ch.angle % math.tau
        if norm_a > math.pi:
            norm_a -= math.tau          # 归一到 [-π, π]
        is_flipped = abs(norm_a) > math.pi * 0.52   # 超过约95°翻转
        is_slow    = ch.vel.length() < 5.0
        if is_flipped and is_slow:
            # 弹簧力推向 0（正立）
            ch.angular_vel += (-norm_a) * 6.0 * DT
            # 稍微往上推，帮助离地
            ch.vel.y = max(ch.vel.y, 1.5)
            particles.emit_spark(ch.pos, color=C.GRN, n=1)

        # 排烟
        if self.alive and abs(self.throttle) > 0.4 and any_ground:
            self._exhaust_t += DT
            if self._exhaust_t > 0.08:
                self._exhaust_t = 0.0
                ch = self.chassis
                cs_, sn_ = math.cos(ch.angle), math.sin(ch.angle)
                ep = pygame.Vector2(
                    ch.pos.x - ch.width * 0.55 * cs_,
                    ch.pos.y - ch.width * 0.55 * sn_ - 0.1,
                )
                col = (80, 78, 75) if self.boost_timer <= 0 else (80, 255, 140)
                particles.emit_exhaust(ep, ch.vel, color=col)

    def _substep(self, terrain, particles, g_scale, fric_scale):
        ch = self.chassis
        g  = 9.8 * g_scale

        ch.vel.y -= g * SUB_DT
        for wh in (self.rear, self.front):
            if wh.detached:
                wh.vel.y -= g * SUB_DT
        if not self.driver.attached:
            self.driver.vel.y -= g * SUB_DT

        _tm = self.cfg.get("tilt_mult", 1.0)
        tilt_pw = (10.0 if self._in_air_time > 0.05 else 7.5) * _tm
        ch.angular_vel += self.tilt * tilt_pw * SUB_DT
        ch.angular_vel *= 0.99

        cs_, sn_ = math.cos(ch.angle), math.sin(ch.angle)
        grounded_cnt = 0
        contact_tan  = None

        for i, wh in enumerate((self.rear, self.front)):
            if wh.detached:
                continue
            local  = self.wheel_offsets[i]
            attach = pygame.Vector2(
                ch.pos.x + local.x * cs_ - local.y * sn_,
                ch.pos.y + local.x * sn_ + local.y * cs_,
            )
            sus_dir = pygame.Vector2(sn_, -cs_)
            ideal   = attach + sus_dir * self.REST_LEN
            gy      = terrain.height(ideal.x)
            n       = terrain.normal(ideal.x)
            wbot    = ideal.y - wh.radius

            if wbot < gy:
                compr = min(self.REST_LEN, gy - wbot)
                wh.grounded = True
                grounded_cnt += 1
                wh.pos = pygame.Vector2(
                    ideal.x - sus_dir.x * compr,
                    ideal.y - sus_dir.y * compr,
                )
                r    = attach - ch.pos
                av   = ch.vel + pygame.Vector2(-r.y, r.x) * ch.angular_vel
                v_n  = av.dot(n)
                force = n * (self.SPRING_K * compr - self.SPRING_DAMP * v_n)
                ch.vel += force / ch.mass * SUB_DT
                torque  = r.x * force.y - r.y * force.x
                ch.angular_vel += torque / ch.inertia * SUB_DT

                if v_n < -self.ROOF_BREAK and self.roof_on:
                    self.roof_on = False
                    particles.emit_debris(ch.pos, color=self.cfg["body"], n=10)
                if v_n < -self.WHEEL_BREAK and not wh.detached and random.random() < 0.4:
                    wh.detached = True
                    wh.vel = pygame.Vector2(ch.vel.x + random.uniform(-4, 4),
                                            ch.vel.y + random.uniform(3, 7))
                    particles.emit_debris(wh.pos, color=(38, 38, 42), n=7)

                tan = pygame.Vector2(n.y, -n.x)
                if tan.x < 0:
                    tan = -tan
                contact_tan = tan
                biome = terrain.biome(attach.x)
                mu    = biome["friction"] * fric_scale
                # 大幅倾斜时减摩擦，方便地面翻滚
                if abs(self.tilt) > 0.8:
                    mu *= 0.45
                v_t   = av.dot(tan)
                ch.vel -= tan * (v_t * mu * 0.0022)

                if abs(v_t) > 8 and random.random() < 0.15:
                    particles.emit_skid(wh.pos)
                if v_n < -3 and random.random() < 0.35:
                    particles.emit_dust(wh.pos, n=max(2, int(-v_n / 2)))
                if v_n < -6 and random.random() < 0.6:
                    pass   # landing 音由 Game 层在 in_air→ground 时触发
            else:
                wh.grounded = False
                wh.pos = ideal

        if self.alive and self.throttle != 0 and grounded_cnt > 0 \
                and contact_tan is not None:
            boost_mult = 3.0 if self.boost_timer > 0 else 1.0
            f = self.cfg["engine"] * self.throttle * boost_mult
            ch.vel += contact_tan * (f / ch.mass * SUB_DT)

        if self.brake:
            ch.vel.x *= 0.93

        # 速度上限：按车辆配置
        MAX_SPEED = self.cfg.get("max_speed_kmh", 240) / 3.6
        if abs(ch.vel.x) > MAX_SPEED:
            ch.vel.x = math.copysign(MAX_SPEED, ch.vel.x)

        ch.pos         += ch.vel * SUB_DT
        ch.angle       += ch.angular_vel * SUB_DT

        for wh in (self.rear, self.front):
            if not wh.detached:
                continue
            wh.pos += wh.vel * SUB_DT
            hit, nrm, pen = terrain.collide_circle(wh.pos.x, wh.pos.y, wh.radius)
            if hit:
                wh.pos += nrm * pen
                vn = wh.vel.dot(nrm)
                if vn < 0:
                    wh.vel -= nrm * (vn * 1.3)
                t2 = pygame.Vector2(nrm.y, -nrm.x)
                wh.vel -= t2 * (wh.vel.dot(t2) * 0.55)

        if self.driver.attached:
            cs2, sn2 = math.cos(ch.angle), math.sin(ch.angle)
            target = pygame.Vector2(
                ch.pos.x + self.driver_offset.x * cs2 - self.driver_offset.y * sn2,
                ch.pos.y + self.driver_offset.x * sn2 + self.driver_offset.y * cs2,
            )
            r2 = target - ch.pos
            tv = ch.vel + pygame.Vector2(-r2.y, r2.x) * ch.angular_vel
            dv = tv - self.driver.vel
            if dv.length() > self.DRIVER_BREAK:
                self.driver.attached = False
                self.driver.vel = self.driver.vel + dv * 0.75
                particles.emit_spark(self.driver.pos, color=C.SKIN, n=18)
            else:
                self.driver.pos = target
                self.driver.vel = tv
        else:
            self.driver.pos += self.driver.vel * SUB_DT
            hit, nrm, pen = terrain.collide_circle(
                self.driver.pos.x, self.driver.pos.y, self.driver.radius)
            if hit:
                self.driver.pos += nrm * pen
                vn = self.driver.vel.dot(nrm)
                if vn < 0:
                    self.driver.vel -= nrm * (vn * 1.3)
                t2 = pygame.Vector2(nrm.y, -nrm.x)
                self.driver.vel -= t2 * (self.driver.vel.dot(t2) * 0.55)

        gy_c = terrain.height(ch.pos.x)
        if ch.pos.y < gy_c - 0.6:
            ch.pos.y = gy_c + 0.4
            if ch.vel.y < 0:
                ch.vel.y *= -0.15

    # ── 车辆绘制（精细版）────────────────────────────────────────
    def draw(self, surf, cam):
        ch = self.chassis
        sa = -ch.angle
        cs_, sn_ = math.cos(sa), math.sin(sa)
        cx, cy   = scr(ch.pos.x, ch.pos.y, cam)
        hw = ch.width  * 0.5 * PPM
        hh = ch.height * 0.5 * PPM

        def rs(px, py):
            return (cx + px * cs_ - py * sn_, cy + px * sn_ + py * cs_)

        # 车底投影阴影
        sw = int(hw * 2.3)
        sh_s = pygame.Surface((sw, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh_s, (0, 0, 0, 55), (0, 0, sw, 10))
        surf.blit(sh_s, (cx - sw // 2, cy + int(hh * 0.9)))

        # 脱落的轮子（车身下层）
        for wh in (self.rear, self.front):
            if wh.detached:
                self._draw_wheel(surf, cam, wh)

        # 底盘主体
        body = [rs(-hw, -hh), rs(hw, -hh), rs(hw, hh), rs(-hw, hh)]
        pygame.draw.polygon(surf, self.cfg["body"], body)

        # 顶部高光条
        hi = lerpC(self.cfg["body"], (255, 255, 255), 0.38)
        pygame.draw.polygon(surf, hi, [rs(-hw, -hh), rs(hw, -hh),
                                       rs(hw, -hh + 6), rs(-hw, -hh + 6)])

        # 侧面装饰条（accent 色）
        if self.cfg["accent"] != self.cfg["body"]:
            pygame.draw.polygon(surf, self.cfg["accent"],
                                [rs(-hw * 0.58, hh * 0.08), rs(hw * 0.72, hh * 0.08),
                                 rs(hw * 0.72, hh * 0.52), rs(-hw * 0.58, hh * 0.52)])

        # 驾驶舱
        if self.roof_on:
            cabin = [
                rs(-hw * 0.52, -hh * 2.18),
                rs( hw * 0.42, -hh * 2.18),
                rs( hw * 0.64, -hh),
                rs(-hw * 0.64, -hh),
            ]
            pygame.draw.polygon(surf, self.cfg["roof"], cabin)
            pygame.draw.polygon(surf, self.cfg["accent"], cabin, 2)

            # 挡风玻璃
            win = [
                rs(-hw * 0.42, -hh * 1.98),
                rs( hw * 0.32, -hh * 1.98),
                rs( hw * 0.50, -hh * 1.10),
                rs(-hw * 0.54, -hh * 1.10),
            ]
            pygame.draw.polygon(surf, self.cfg["glass"], win)

            # 玻璃反光
            gl_hi = lerpC(self.cfg["glass"], (255, 255, 255), 0.62)
            pygame.draw.polygon(surf, gl_hi,
                                [rs(-hw * 0.40, -hh * 1.90),
                                 rs(-hw * 0.10, -hh * 1.90),
                                 rs(-hw * 0.14, -hh * 1.35),
                                 rs(-hw * 0.46, -hh * 1.35)])

        # 轮弧：跟随实际轮子屏幕坐标，不悬空
        arch_col = lerpC(self.cfg["body"], (0, 0, 0), 0.42)
        for wh in (self.rear, self.front):
            if not wh.detached:
                wx_a, wy_a = scr(wh.pos.x, wh.pos.y, cam)
                wr = int(wh.radius * PPM * 1.32)
                pygame.draw.circle(surf, arch_col, (wx_a, wy_a), wr)

        # 边框
        pygame.draw.polygon(surf, self.cfg["accent"], body, 2)

        # 头灯
        hl = rs(hw * 0.88, hh * 0.22)
        pygame.draw.circle(surf, C.YEL, (int(hl[0]), int(hl[1])), 5)
        pygame.draw.circle(surf, (255, 255, 200), (int(hl[0]), int(hl[1])), 3)

        # 尾灯
        tl = rs(-hw * 0.88, hh * 0.22)
        pygame.draw.circle(surf, C.RED, (int(tl[0]), int(tl[1])), 4)

        # 附着轮子（车身上层）
        for wh in (self.rear, self.front):
            if not wh.detached:
                self._draw_wheel(surf, cam, wh)

        self._draw_driver(surf, cam)

    def _draw_wheel(self, surf, cam, wh):
        wx, wy = scr(wh.pos.x, wh.pos.y, cam)
        r = int(wh.radius * PPM)
        pygame.draw.circle(surf, (20, 20, 24), (wx, wy), r)
        pygame.draw.circle(surf, (40, 40, 46), (wx, wy), r, 3)
        pygame.draw.circle(surf, (88, 88, 98), (wx, wy), max(2, r - 4))
        pygame.draw.circle(surf, (58, 58, 66), (wx, wy), max(1, r - 7), 2)
        for k in range(5):
            a  = wh.spin + k * math.tau / 5
            ix = wx + int(math.cos(a) * (r - 4))
            iy = wy + int(math.sin(a) * (r - 4))
            pygame.draw.line(surf, (52, 52, 62), (wx, wy), (ix, iy), 2)
        pygame.draw.circle(surf, (30, 30, 34), (wx, wy), r, 2)

    def _draw_driver(self, surf, cam):
        dx, dy = scr(self.driver.pos.x, self.driver.pos.y, cam)
        r = int(self.driver.radius * PPM)
        pygame.draw.circle(surf, C.SKIN, (dx, dy), r)
        pygame.draw.arc(surf, C.RED,
                        (dx - r - 2, dy - r - 3, (r + 2) * 2, (r + 2) * 2),
                        0.2, math.pi - 0.2, 4)
        if self.driver.attached:
            pygame.draw.circle(surf, (75, 125, 195), (dx + r // 3, dy - 1), max(1, r // 3))
        else:
            pygame.draw.line(surf, C.RED, (dx - 2, dy - 2), (dx + 2, dy + 2), 2)
            pygame.draw.line(surf, C.RED, (dx + 2, dy - 2), (dx - 2, dy + 2), 2)
        pygame.draw.circle(surf, C.DGRAY, (dx, dy), r, 1)


# ════════════════════════════ 相机 ════════════════════════════════
class Camera:
    def __init__(self):
        self.pos   = pygame.Vector2(0, 0)
        self.shake = 0.0
        self._off  = pygame.Vector2(0, 0)

    def follow(self, tgt, lookahead_vx=0.0):
        tx = tgt.x * PPM + lookahead_vx * 0.12
        ty = tgt.y * PPM
        self.pos.x = lerp(self.pos.x, tx, 0.14)
        self.pos.y = lerp(self.pos.y, ty, 0.10)

    def add_shake(self, amount):
        self.shake = max(self.shake, amount)

    def step(self, dt):
        if self.shake > 0:
            self._off.x = random.uniform(-self.shake, self.shake)
            self._off.y = random.uniform(-self.shake, self.shake)
            self.shake  = max(0, self.shake - 100 * dt)
        else:
            self._off.update(0, 0)

    @property
    def x(self): return self.pos.x + self._off.x
    @property
    def y(self): return self.pos.y + self._off.y


# ════════════════════════════ 音频系统 ════════════════════════════════
class Audio:
    """
    文件目录：game/assets/audio/
    bgm_race.ogg, engine_idle.wav, engine_high.wav,
    crash_metal.wav, break_wood.wav, flip_combo.wav,
    landing_heavy.wav, boost.ogg, ui_click.wav
    """
    def __init__(self, asset_dir=None, music_volume=0.45, sfx_volume=0.75):
        self.ok = False
        self.music_loaded = False
        self.music_volume = float(music_volume)
        self.sfx_volume   = float(sfx_volume)
        self.sounds       = {}
        self.engine_idle  = None
        self.engine_high  = None
        self.engine_idle_ch  = None
        self.engine_high_ch  = None
        self.engine_started  = False
        base = _resource_dir()
        default_dirs = [
            base / "game" / "assets" / "audio",
            base / "assets" / "audio",
        ]
        self.asset_dir = Path(asset_dir) if asset_dir else next(
            (p for p in default_dirs if p.exists()), default_dirs[0])
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(44100, -16, 2, 128)
                pygame.mixer.init()
            pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
            self.ok = True
        except Exception:
            return
        self._load_all()
        self.start_music()

    def _first(self, *names):
        for name in names:
            p = self.asset_dir / name
            if p.exists():
                return p
        return None

    def _load(self, key, *filenames):
        if not self.ok:
            return None
        path = self._first(*filenames)
        if not path:
            return None
        try:
            snd = pygame.mixer.Sound(str(path))
            snd.set_volume(self.sfx_volume)
            self.sounds[key] = snd
            return snd
        except Exception:
            return None

    def _load_all(self):
        self.engine_idle = self._load("engine_idle",
            "engine_idle.wav", "engine_idle.ogg", "loop_0.wav")
        self.engine_high = self._load("engine_high",
            "engine_high.wav", "engine_high.ogg", "loop_5.wav", "loop_5_0.wav")
        self._load("crash_metal", "crash_metal.ogg", "crash_metal.wav", "metal_hit.wav")
        self._load("break_wood",  "break_wood.ogg",  "break_wood.wav",  "wood_break.wav")
        self._load("flip",        "flip_combo.ogg",  "flip_combo.wav",  "level_up.wav")
        self._load("landing",     "landing_heavy.ogg","landing_heavy.wav","jumpland.wav")
        self._load("boost",       "boost.ogg",        "boost.wav",       "boost_start.ogg")
        self._load("click",       "ui_click.ogg",     "ui_click.wav",    "click.wav")
        self._load("ding",        "ding.ogg",    "ding.wav")
        # 兼容旧名字
        self.sounds.setdefault("crash", self.sounds.get("crash_metal"))
        self.sounds.setdefault("start", self.sounds.get("click"))

    def start_music(self, loops=-1):
        if not self.ok:
            return
        path = self._first("bgm_race.ogg","bgm_race.mp3","bgm_race.wav",
                            "pixel_sprinter_loop.ogg","pixel_sprinter_loop_0.ogg")
        if not path:
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(self.music_volume)
            pygame.mixer.music.play(loops)
            self.music_loaded = True
        except Exception:
            pass

    def stop_music(self):
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def play(self, name, vol=1.0):
        if not self.ok:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            snd.set_volume(max(0.0, min(1.0, self.sfx_volume * float(vol))))
            snd.play()
        except Exception:
            pass

    def update_engine(self, speed_kmh, throttle):
        """每帧调用，实时混合怠速和高速引擎声"""
        if not self.ok or self.engine_idle is None or self.engine_high is None:
            return
        spd = max(0.0, float(speed_kmh))
        th  = max(0.0, min(1.0, abs(float(throttle))))
        t   = max(0.0, min(1.0, spd / 160.0))
        act = max(0.16, th)
        idle_vol = min(0.55, max(0.0, (0.35 * (1.0 - t) + 0.08) * act * self.sfx_volume))
        high_vol = min(0.70, max(0.0, (0.08 + 0.70 * t)         * act * self.sfx_volume))
        try:
            if not self.engine_started:
                self.engine_idle_ch = self.engine_idle.play(loops=-1)
                self.engine_high_ch = self.engine_high.play(loops=-1)
                self.engine_started = True
            if self.engine_idle_ch:
                self.engine_idle_ch.set_volume(idle_vol)
            if self.engine_high_ch:
                self.engine_high_ch.set_volume(high_vol)
        except Exception:
            pass

    def stop_engine(self):
        try:
            if self.engine_idle_ch: self.engine_idle_ch.stop()
            if self.engine_high_ch: self.engine_high_ch.stop()
        except Exception:
            pass
        self.engine_idle_ch = self.engine_high_ch = None
        self.engine_started = False

# ════════════════════════════ 排行榜 ════════════════════════════════
# ════════════════════════════ 番茄钟日志 ════════════════════════════
def pomo_log_load():
    """加载番茄钟历史。结构: {"sessions": [{"date","start","minutes","completed"}, ...]}"""
    if not POMO_LOG_PATH.exists():
        return {"sessions": []}
    try:
        with open(POMO_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("sessions", [])
        return data
    except Exception:
        return {"sessions": []}


def pomo_log_save(data):
    try:
        with open(POMO_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def pomo_log_add(data, minutes, completed=True):
    """追加一条专注记录"""
    import datetime
    now = datetime.datetime.now()
    data.setdefault("sessions", []).append({
        "date":      now.date().isoformat(),
        "start":     now.strftime("%H:%M"),
        "minutes":   int(minutes),
        "completed": bool(completed),
    })
    pomo_log_save(data)


def pomo_log_stats(data):
    """计算统计：今日数、本周数、本周分钟、总数、总分钟、连续打卡天数"""
    import datetime
    sessions = [s for s in data.get("sessions", []) if s.get("completed")]
    today    = datetime.date.today()
    week_ago = today - datetime.timedelta(days=6)   # 含今天共 7 天

    today_count = sum(1 for s in sessions if s["date"] == today.isoformat())
    today_min   = sum(s["minutes"] for s in sessions if s["date"] == today.isoformat())
    week_count  = sum(1 for s in sessions
                      if datetime.date.fromisoformat(s["date"]) >= week_ago)
    week_min    = sum(s["minutes"] for s in sessions
                      if datetime.date.fromisoformat(s["date"]) >= week_ago)
    total_count = len(sessions)
    total_min   = sum(s["minutes"] for s in sessions)

    # 连续打卡：从今天往回，每天至少 1 个完成的专注
    dates = {s["date"] for s in sessions}
    streak = 0
    d = today
    while d.isoformat() in dates:
        streak += 1
        d -= datetime.timedelta(days=1)

    return {
        "today_count": today_count,
        "today_min":   today_min,
        "week_count":  week_count,
        "week_min":    week_min,
        "total_count": total_count,
        "total_min":   total_min,
        "streak":      streak,
    }


# ════════════════════════════ 地形渲染 ════════════════════════════
def draw_terrain(surf, terrain, cam):
    lx = (cam.x - W * 0.35) / PPM - 2
    rx = (cam.x + W * 0.65) / PPM + 2
    step = 0.45
    pts  = []
    x = lx
    while x <= rx:
        y  = terrain.height(x)
        sx_, sy_ = scr(x, y, cam)
        pts.append((sx_, sy_, x))
        x += step
    if len(pts) < 2:
        return

    mid_x      = (lx + rx) * 0.5
    _tb0, _tb1, _tbt = get_biome_blend(mid_x)
    b          = _tb0  # 用于装饰类型判断
    g0 = lerpC(_tb0["g0"], _tb1["g0"], _tbt)
    g1 = lerpC(_tb0["g1"], _tb1["g1"], _tbt)
    g2 = lerpC(_tb0["g2"], _tb1["g2"], _tbt)
    top    = [(p[0], p[1]) for p in pts]
    bot_y  = H + 20

    # 最深层
    pygame.draw.polygon(surf, g2, top + [(W + 20, bot_y), (-20, bot_y)])
    # 中层
    mid_off = 45
    mid_top = [(p[0], p[1] + mid_off) for p in pts]
    pygame.draw.polygon(surf, g1, mid_top + [(W + 20, bot_y), (-20, bot_y)])
    # 顶层薄带
    band_h = 20
    band   = top + [(p[0], p[1] + band_h) for p in reversed(pts)]
    pygame.draw.polygon(surf, g0, band)
    # 高光线
    hi_col = lerpC(g0, (255, 255, 255), 0.30)
    pygame.draw.lines(surf, hi_col, False, top, 2)

    # 地面装饰：用固定世界坐标间距采样，避免高速时密集闪烁
    # 草地：树 每12m一棵，灌木丛 每5m一簇；其他场景每4m一个特征
    if b["name"] == "GRASSLAND":
        decor_step = 0.9   # 采样步长（世界单位）
    else:
        decor_step = 0.9

    # 把 pts 重新按世界坐标 snap 到固定格点，避免相机偏移导致闪烁
    snap = decor_step
    lx_snap = math.floor(lx / snap) * snap
    dx_snap = snap
    wx_ = lx_snap
    # 建立 wx→屏幕坐标 的快速查找（线性插值）
    def get_sy(wx_val):
        y_val = terrain.height(wx_val)
        return scr(wx_val, y_val, cam)

    while wx_ <= rx:
        rng_d = random.Random(int(wx_ * 100 + 0.5))

        if b["name"] == "GRASSLAND":
            # 草丛（程序绘制，4.5m一丛）
            g_slot = int(wx_ / 3.0 + 0.5)
            rng_g  = random.Random(g_slot * 7919)
            g_wx   = g_slot * 3.0 + rng_g.uniform(-1.5, 1.5)
            if rng_g.random() < 0.38 and abs(wx_ - g_wx) < snap * 0.6:
                sx2, sy2 = get_sy(g_wx)
                ofs = rng_g.randint(-4, 4)
                for k in range(rng_g.randint(2, 4)):
                    gh = rng_g.randint(5, 12)
                    pygame.draw.line(surf, b["g2"],
                                     (sx2 + ofs + k * 4 - 4, sy2),
                                     (sx2 + ofs + k * 4 - 4, sy2 - gh), 1)

            # 树：每约 14m 一棵
            # 草丛精灵（bush / plant，每 1.8m）
            bush_slot = int(wx_ / 4.0 + 0.5)
            rng_b     = random.Random(bush_slot * 13337)
            bush_wx   = bush_slot * 4.0 + rng_b.uniform(-2.0, 2.0)
            if rng_b.random() < 0.35 and abs(wx_ - bush_wx) < snap * 0.6:
                sx2, sy2 = get_sy(bush_wx)
                sname = "bush" if rng_b.random() < 0.6 else "plant"
                blit_sprite(surf, sname, sx2, sy2)
            # 树（每 14m）
            tree_slot = int(wx_ / 5.0 + 0.5)
            rng_tree  = random.Random(tree_slot * 31337)
            tree_wx   = tree_slot * 5.0 + rng_tree.uniform(-2.0, 2.0)
            if rng_tree.random() < 0.22 and abs(wx_ - tree_wx) < snap * 0.6:
                sx2, sy2 = get_sy(tree_wx)
                # 精灵树：用 pine 放大一点模拟阔叶树，或程序画
                img_t = SPRITE_S.get("pine")
                if img_t:
                    scale_t = rng_tree.uniform(1.4, 2.0)
                    w_t = int(img_t.get_width()  * scale_t)
                    h_t = int(img_t.get_height() * scale_t)
                    # 草地树：染成绿色
                    img_scaled = pygame.transform.scale(img_t, (w_t, h_t))
                    surf.blit(img_scaled, (sx2 - w_t // 2, sy2 - h_t))
                else:
                    th = rng_tree.randint(22, 40)
                    tw = int(th * 0.55)
                    pygame.draw.rect(surf, (78, 52, 28), (sx2-2, sy2-th//3, 4, th//3+2))
                    pygame.draw.polygon(surf, (38,105,34),
                        [(sx2,sy2-th-4),(sx2-tw,sy2-th//3+2),(sx2+tw,sy2-th//3+2)])

        elif b["name"] == "ICE":
            # 冰晶 / 松树 精灵（每 5m）
            slot = int(wx_ / 4.0 + 0.5)
            rng_slot = random.Random(slot * 8887)
            slot_wx_ = slot * 4.0 + rng_slot.uniform(-2.0, 2.0)
            if rng_slot.random() < 0.36 and abs(wx_ - slot_wx_) < snap * 0.6:
                sx2, sy2 = get_sy(slot_wx_)
                sname_ = "pine" if rng_slot.random() < 0.5 else "snowball"
                sc_ = rng_slot.uniform(0.75, 1.25)
                img_ = SPRITE_S.get(sname_)
                if img_:
                    w_ = int(img_.get_width()  * sc_)
                    h_ = int(img_.get_height() * sc_)
                    surf.blit(pygame.transform.scale(img_, (w_, h_)),
                              (sx2 - w_//2, sy2 - h_))
                else:
                    ic = lerpC(b["g0"], (255,255,255), 0.65)
                    h2_ = rng_slot.randint(6, 14)
                    pygame.draw.polygon(surf, ic,
                        [(sx2-3, sy2),(sx2, sy2-h2_),(sx2+3, sy2)])

        elif b["name"] == "MOON":
            # 月球岩石（每 7m）
            slot_m = int(wx_ / 4.0 + 0.5)
            rng_m  = random.Random(slot_m * 5501)
            moon_wx = slot_m * 4.0 + rng_m.uniform(-2.0, 2.0)
            if rng_m.random() < 0.33 and abs(wx_ - moon_wx) < snap * 0.6:
                sx2, sy2 = get_sy(moon_wx)
                sc_m = rng_m.uniform(0.7, 1.2)
                img_m = SPRITE_S.get("moon_rock")
                if img_m:
                    w_m = int(img_m.get_width()  * sc_m)
                    h_m = int(img_m.get_height() * sc_m)
                    surf.blit(pygame.transform.scale(img_m, (w_m, h_m)),
                              (sx2 - w_m//2, sy2 - h_m))

        elif b["name"] == "VOLCANO":
            # 岩浆石块（8m间距，大小随机）
            v_slot = int(wx_ / 4.0 + 0.5)
            rng_v  = random.Random(v_slot * 9973)
            v_wx   = v_slot * 4.0 + rng_v.uniform(-2.0, 2.0)
            if rng_v.random() < 0.40 and abs(wx_ - v_wx) < snap * 0.6:
                sx2, sy2 = get_sy(v_wx)
                vc = rng_v.choice([(210, 80, 20), (178, 48, 10), (255, 118, 28)])
                sz = rng_v.randint(4, 11)
                pygame.draw.polygon(surf, vc,
                                    [(sx2 - sz, sy2), (sx2 - sz//2, sy2 - sz*2),
                                     (sx2 + sz//2, sy2 - sz*2+2), (sx2 + sz, sy2)])

        elif b["name"] == "DESERT":
            # 仙人掌精灵（每 9m）
            cact_slot = int(wx_ / 4.0 + 0.5)
            rng_c     = random.Random(cact_slot * 14983)
            cact_wx   = cact_slot * 4.0 + rng_c.uniform(-2.0, 2.0)
            if rng_c.random() < 0.42 and abs(wx_ - cact_wx) < dx_snap * 0.6:
                sx2, sy2 = get_sy(cact_wx)
                sc = rng_c.uniform(0.85, 1.35)
                img_c = SPRITE_S.get("cactus")
                if img_c:
                    w_c = int(img_c.get_width()  * sc)
                    h_c = int(img_c.get_height() * sc)
                    surf.blit(pygame.transform.scale(img_c, (w_c, h_c)),
                              (sx2 - w_c//2, sy2 - h_c))
                else:
                    pygame.draw.rect(surf, (72,120,55), (sx2-2, sy2-28, 4, 28))
            # 沙纹弧线（6m间距）
            sand_slot = int(wx_ / 3.0 + 0.5)
            rng_s     = random.Random(sand_slot * 7321)
            sand_wx   = sand_slot * 3.0 + rng_s.uniform(-1.5, 1.5)
            if rng_s.random() < 0.38 and abs(wx_ - sand_wx) < snap * 0.6:
                sx2, sy2 = get_sy(sand_wx)
                sw = rng_s.randint(10, 24)
                pygame.draw.arc(surf, (185, 148, 80),
                                (sx2 - sw//2, sy2 - 3, sw, 5), 0, math.pi, 1)

        elif b["name"] == "DEEP_SEA":
            # 海草精灵（每 9m，只用绿色系两种）
            sw_slot = int(wx_ / 4.0 + 0.5)
            rng_sw  = random.Random(sw_slot * 11113)
            sw_wx   = sw_slot * 4.0 + rng_sw.uniform(-2.0, 2.0)
            if rng_sw.random() < 0.38 and abs(wx_ - sw_wx) < snap * 0.6:
                sx2, sy2 = get_sy(sw_wx)
                sn_ = rng_sw.choice(["seaweed_a", "seaweed_b"])
                sc_ = rng_sw.uniform(0.8, 1.0)
                img_ = SPRITE_S.get(sn_)
                if img_:
                    w_ = int(img_.get_width()  * sc_)
                    h_ = int(img_.get_height() * sc_)
                    surf.blit(pygame.transform.scale(img_, (w_, h_)),
                              (sx2 - w_//2, sy2 - h_))
            # 岩石（每 20m，单点绘制）
            rock_slot = int(wx_ / 7.0 + 0.5)
            rng_r2    = random.Random(rock_slot * 8831)
            rock_wx   = rock_slot * 7.0 + rng_r2.uniform(-3.0, 3.0)
            if rng_r2.random() < 0.30 and abs(wx_ - rock_wx) < snap * 0.6:
                sx2, sy2 = get_sy(rock_wx)
                sn_r = rng_r2.choice(["sea_rock_a", "sea_rock_b"])
                blit_sprite(surf, sn_r, sx2, sy2)
            # 小鱼（每 35m，稀少出现）
            fish_slot = int(wx_ / 35.0 + 0.5)
            rng_f     = random.Random(fish_slot * 7717)
            fish_wx   = fish_slot * 35.0 + rng_f.uniform(-4.0, 4.0)
            if rng_f.random() < 0.65 and abs(wx_ - fish_wx) < snap * 0.6:
                sx2, sy2 = get_sy(fish_wx)
                fy_off = rng_f.randint(30, 90)
                sn_f   = rng_f.choice(["fish_blue", "fish_orange"])
                img_f  = SPRITE_S.get(sn_f)
                if img_f:
                    img_draw = pygame.transform.flip(img_f, fish_slot % 2 == 0, False)
                    surf.blit(img_draw, (sx2 - img_f.get_width()//2, sy2 - fy_off))

        elif b["name"] == "NEON":
            # 路灯（程序绘制，细竿+灯头）
            lamp_slot = int(wx_ / 7.0 + 0.5)
            rng_lamp  = random.Random(lamp_slot * 6173)
            lamp_wx   = lamp_slot * 7.0 + rng_lamp.uniform(-3.0, 3.0)
            if rng_lamp.random() < 0.30 and abs(wx_ - lamp_wx) < snap * 0.6:
                sx2, sy2 = get_sy(lamp_wx)
                pole_h = rng_lamp.randint(55, 75)
                # 路灯竿
                pygame.draw.line(surf, (85, 88, 105),
                                 (sx2, sy2), (sx2, sy2 - pole_h), 2)
                # 灯头横臂
                arm_len = rng_lamp.randint(10, 18)
                pygame.draw.line(surf, (85, 88, 105),
                                 (sx2, sy2 - pole_h),
                                 (sx2 + arm_len, sy2 - pole_h + 8), 2)
                # 灯光（霓虹色）
                lc = rng_lamp.choice([(0, 220, 255), (255, 50, 200), (80, 255, 120)])
                pygame.draw.circle(surf, lc, (sx2 + arm_len, sy2 - pole_h + 10), 4)
            # 地面霓虹线（短彩色横线，有长有短）
            line_slot = int(wx_ / 3.0 + 0.5)
            rng_line  = random.Random(line_slot * 3371)
            line_wx   = line_slot * 3.0 + rng_line.uniform(-1.5, 1.5)
            if rng_line.random() < 0.35 and abs(wx_ - line_wx) < snap * 0.6:
                sx2, sy2 = get_sy(line_wx)
                lw = rng_line.randint(5, 18)
                nc = rng_line.choice([(0, 220, 255), (255, 50, 200), (80, 255, 120)])
                pygame.draw.line(surf, nc, (sx2 - lw, sy2), (sx2 + lw, sy2), 2)

        elif b["name"] == "CANDY":
            # 棒棒糖精灵（每 8m）
            lol_slot = int(wx_ / 4.0 + 0.5)
            rng_l    = random.Random(lol_slot * 15497)
            lol_wx   = lol_slot * 4.0 + rng_l.uniform(-2.0, 2.0)
            if abs(wx_ - lol_wx) < dx_snap * 0.6:
                sx2, sy2 = get_sy(lol_wx)
                sc_l = rng_l.uniform(0.9, 1.4)
                sn_l = rng_l.choice(["lollipop_red","lollipop_green","cane_pink"])
                img_l = SPRITE_S.get(sn_l)
                if img_l:
                    w_l = int(img_l.get_width()  * sc_l)
                    h_l = int(img_l.get_height() * sc_l)
                    surf.blit(pygame.transform.scale(img_l,(w_l,h_l)),
                              (sx2 - w_l//2, sy2 - h_l))
            # 小装饰（cupcake / heart / cherry，每 5m）
            deco_slot = int(wx_ / 6.0 + 0.5)
            rng_d2    = random.Random(deco_slot * 22271)
            deco_wx   = deco_slot * 6.0 + rng_d2.uniform(-3.0, 3.0)
            if rng_d2.random() < 0.28 and abs(wx_ - deco_wx) < snap * 0.6:
                sx2, sy2 = get_sy(deco_wx)
                sn_d = rng_d2.choice(["cupcake","heart","cherry"])
                blit_sprite(surf, sn_d, sx2, sy2)
            # 彩色地面小点
            dot_slot = int(wx_ / 1.5 + 0.5)
            rng_dot  = random.Random(dot_slot * 9901)
            if rng_dot.random() < 0.35:
                sx2, sy2 = get_sy(wx_)
                dc = rng_dot.choice([(255,100,180),(255,240,80),(180,120,255),(80,220,200)])
                pygame.draw.circle(surf, dc, (sx2, sy2 - 1), 2)

        wx_ += dx_snap


# ════════════════════════════ 加速板 / 路面杂物渲染 ════════════════
def draw_pickups(surf, cam, boosts, debris, t_now):
    # 加速板
    for b in boosts:
        if b.get("taken"):
            continue
        sx_, sy_ = scr(b["x"], b["y"], cam)
        if not (-45 < sx_ < W + 45):
            continue
        glow = int(abs(math.sin(t_now * 3.5)) * 65 + 155)
        col  = (0, glow, int(glow * 0.62))
        for k in range(3):
            ox = sx_ - 18 + k * 18
            pygame.draw.polygon(surf, col,
                                [(ox, sy_ + 7), (ox + 9, sy_ - 9), (ox + 18, sy_ + 7)])
            pygame.draw.polygon(surf, C.BOOST,
                                [(ox, sy_ + 7), (ox + 9, sy_ - 9), (ox + 18, sy_ + 7)], 2)

    # 路面杂物
    for d in debris:
        if d.get("smashed"):
            continue
        sx_, sy_ = scr(d["x"], d["y"], cam)
        if not (-55 < sx_ < W + 55):
            continue
        rs_ = int(d["r"] * PPM)
        col, col2 = d["col"], d["col2"]
        kind = d["kind"]
        rot  = d.get("rot", 0)

        if kind == "crate":
            hw, hh = int(rs_ * 1.4), int(rs_ * 1.2)
            cs2, sn2 = math.cos(rot), math.sin(rot)
            corners = [(-hw,-hh),(hw,-hh),(hw,hh),(-hw,hh)]
            pts_ = [(sx_+int(x*cs2-y*sn2), sy_+int(x*sn2+y*cs2)) for x,y in corners]
            pygame.draw.polygon(surf, col, pts_)
            pygame.draw.line(surf, col2, pts_[0], pts_[2], 2)
            pygame.draw.line(surf, col2, pts_[1], pts_[3], 2)
            pygame.draw.polygon(surf, col2, pts_, 2)

        elif kind == "barrel":
            pygame.draw.ellipse(surf, col,
                                (sx_ - rs_, sy_ - int(rs_*1.5), rs_*2, int(rs_*3)))
            pygame.draw.ellipse(surf, col2,
                                (sx_ - rs_, sy_ - int(rs_*1.5), rs_*2, int(rs_*3)), 2)
            for yoff in [-rs_//2, 0, rs_//2]:
                pygame.draw.line(surf, col2,
                                 (sx_ - rs_ + 2, sy_ + yoff),
                                 (sx_ + rs_ - 2, sy_ + yoff), 2)

        elif kind == "cone":
            base_w = int(rs_ * 2.2)
            h_     = int(rs_ * 3.0)
            pts_   = [(sx_, sy_ - h_), (sx_ - base_w//2, sy_), (sx_ + base_w//2, sy_)]
            pygame.draw.polygon(surf, col, pts_)
            mid_y = sy_ - h_//3
            pygame.draw.line(surf, col2,
                             (sx_ - base_w//4, mid_y),
                             (sx_ + base_w//4, mid_y), 3)
            pygame.draw.polygon(surf, col2, pts_, 2)

        elif kind == "box":
            hw2 = int(rs_ * 1.2)
            pts_ = [(sx_-hw2, sy_-hw2),(sx_+hw2, sy_-hw2),
                    (sx_+hw2, sy_+hw2),(sx_-hw2, sy_+hw2)]
            pygame.draw.polygon(surf, col, pts_)
            pygame.draw.line(surf, col2, (sx_, sy_-hw2), (sx_, sy_+hw2), 2)
            pygame.draw.line(surf, col2, (sx_-hw2, sy_), (sx_+hw2, sy_), 2)
            pygame.draw.polygon(surf, col2, pts_, 1)

        elif kind == "sign":
            pygame.draw.polygon(surf, col,
                                [(sx_, sy_ - rs_*2), (sx_ + rs_, sy_),
                                 (sx_, sy_ + rs_*2), (sx_ - rs_, sy_)])
            pygame.draw.polygon(surf, col2,
                                [(sx_, sy_ - rs_*2), (sx_ + rs_, sy_),
                                 (sx_, sy_ + rs_*2), (sx_ - rs_, sy_)], 2)
            pygame.draw.line(surf, col2, (sx_, sy_ - rs_), (sx_, sy_ + rs_//3), 2)
            pygame.draw.circle(surf, col2, (sx_, sy_ + int(rs_*0.9)), 2)

        elif kind == "beat":
            # 节拍标记：发光脉冲菱形
            pulse = abs(math.sin(t_now * math.pi * 2))
            rs_b  = int(rs_ * (1.0 + pulse * 0.3))
            pygame.draw.polygon(surf, (*col, int(180 + 75 * pulse)),
                                [(sx_, sy_ - rs_b*2), (sx_ + rs_b, sy_),
                                 (sx_, sy_ + rs_b*0.5), (sx_ - rs_b, sy_)])
            # 外发光圈
            glow_s = pygame.Surface((rs_b*4+4, rs_b*4+4), pygame.SRCALPHA)
            pygame.draw.circle(glow_s, (*col, int(40 * pulse)),
                               (rs_b*2+2, rs_b*2+2), rs_b*2)
            surf.blit(glow_s, (sx_ - rs_b*2 - 2, sy_ - rs_b*2 - 2))
            pygame.draw.polygon(surf, col2,
                                [(sx_, sy_ - rs_b*2), (sx_ + rs_b, sy_),
                                 (sx_, sy_ + rs_b*0.5), (sx_ - rs_b, sy_)], 2)


def draw_lava_jets(surf, cam, jets, t_now):
    for j in jets:
        phase = (t_now - j["t0"]) % j["period"]
        if phase > j["dur"]:
            continue
        sx_, sy_ = scr(j["x"], j["y"], cam)
        if not (-65 < sx_ < W + 65):
            continue
        intensity = 1.0 - abs((phase / j["dur"]) - 0.5) * 2
        h = int(135 * intensity)
        for _ in range(10):
            ox  = sx_ + random.randint(-8, 8)
            col = random.choice([C.LAVA, C.ORG, C.YEL])
            pygame.draw.line(surf, col, (ox, sy_),
                             (ox + random.randint(-9, 9),
                              sy_ - h + random.randint(-13, 13)), 3)


# ════════════════════════════ HUD ════════════════════════════════
def _panel(surf, x, y, w, h, alpha=175, radius=10, accent=None):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    # 主体：深色玻璃
    pygame.draw.rect(s, (6, 7, 16, alpha), (0, 0, w, h), border_radius=radius)
    # 顶部高光条
    pygame.draw.rect(s, (255, 255, 255, 22), (1, 1, w - 2, h // 3), border_radius=radius)
    # 外边框
    border_col = (*accent, 90) if accent else (255, 255, 255, 38)
    pygame.draw.rect(s, border_col, (0, 0, w, h), 1, border_radius=radius)
    # 底部彩色线（accent）
    if accent:
        pygame.draw.rect(s, (*accent, 160), (2, h - 3, w - 4, 2), border_radius=2)
    surf.blit(s, (x, y))


def draw_hud(surf, car, dist_m, terrain, font, big, huge, tiny):
    kmh = int(car.speed_kmh())

    # ── 翻滚闪光
    if car.flip_flash > 0:
        flash_alpha = int(car.flip_flash / 0.45 * 100)
        fl = pygame.Surface((W, H), pygame.SRCALPHA)
        fl.fill((255, 200, 50, flash_alpha))
        surf.blit(fl, (0, 0))

    # ── 高速动感线（边缘光晕效果）
    if kmh > 80:
        streak_alpha = min(160, int((kmh - 80) * 2.0))
        n_streaks    = min(16, int((kmh - 80) * 0.20))
        rng_st       = random.Random(int(car.chassis.pos.x * 3))
        s_ov = pygame.Surface((W, H), pygame.SRCALPHA)
        for _ in range(n_streaks):
            sy_  = rng_st.randint(60, H - 60)
            lx_  = rng_st.randint(0, 100)
            ln_  = rng_st.randint(50, 160)
            alp  = int(streak_alpha * rng_st.uniform(0.25, 0.9))
            pygame.draw.line(s_ov, (255, 255, 255, alp), (lx_, sy_), (lx_ + ln_, sy_), 1)
            pygame.draw.line(s_ov, (255, 255, 255, alp), (W-lx_-ln_, sy_), (W-lx_, sy_), 1)
        surf.blit(s_ov, (0, 0))

    # ── 翻滚完成动画
    if car.flip_text_timer > 0:
        t_fade   = car.flip_text_timer / 1.2
        scale    = 1.0 + 0.45 * math.sin(t_fade * math.pi)
        alpha    = int(255 * min(1.0, t_fade * 2))
        flip_col = lerpC(C.ORG, C.YEL, t_fade)
        base_s   = huge.render(f"FLIP x{car.score_flips}!", True, flip_col)
        bw = int(base_s.get_width() * scale)
        bh = int(base_s.get_height() * scale)
        if bw > 0 and bh > 0:
            sc = pygame.transform.scale(base_s, (bw, bh))
            sc.set_alpha(alpha)
            surf.blit(sc, sc.get_rect(center=(W // 2, H // 2 - 60)))

    # ── 左侧：距离 + 速度（合并在一个宽面板里）
    sp_col = C.GRN if kmh < 80 else (C.YEL if kmh < 145 else C.RED)
    _panel(surf, 12, 10, 340, 70, alpha=210, accent=sp_col)
    # 距离（左）
    surf.blit(tiny.render("距离", True, (165, 200, 240)), (22, 14))
    surf.blit(big.render(f"{int(dist_m)} m", True, C.WHITE), (22, 32))
    # 分隔线
    pygame.draw.line(surf, (60, 65, 80), (185, 16), (185, 70), 1)
    # 速度（右）
    surf.blit(tiny.render("速度", True, lerpC((165,200,240), sp_col, 0.7)), (196, 14))
    surf.blit(big.render(str(kmh), True, sp_col), (196, 32))
    surf.blit(tiny.render("km/h", True, (155, 162, 178)),
              (196 + big.size(str(kmh))[0] + 4, 46))
    # 速度条（细线，在面板底部）
    max_spd = car.cfg.get("max_speed_kmh", 240)
    bar_ratio = min(1.0, kmh / max_spd)
    bar_x, bar_y, bar_w = 14, 74, 340
    pygame.draw.rect(surf, (30, 34, 44), (bar_x, bar_y, bar_w, 4), border_radius=2)
    if bar_ratio > 0:
        pygame.draw.rect(surf, sp_col, (bar_x, bar_y, int(bar_w * bar_ratio), 4), border_radius=2)

    # ── 右上：连击
    if car.score_flips > 0:
        fc = C.YEL if car.score_flips < 5 else (C.ORG if car.score_flips < 10 else C.PINK)
        _panel(surf, W - 170, 10, 158, 70, alpha=210, accent=fc)
        surf.blit(tiny.render("连击", True, lerpC((155,162,178), fc, 0.6)), (W - 160, 14))
        surf.blit(big.render(f"x{car.score_flips}", True, fc), (W - 160, 32))

    # ── 右上：场景标签（连击下方）
    _hb0, _hb1, _ht = get_biome_blend(dist_m)
    _hlabel = _hb0["label"] if _ht < 0.5 else _hb1["label"]
    _panel(surf, W - 170, 86, 158, 32, alpha=200, accent=(160, 165, 185))
    surf.blit(tiny.render(_hlabel, True, (230, 235, 248)),
              surf.blit(tiny.render("", True, C.WHITE), (0,0)) and (0,0) or (W - 160, 94))

    # ── 加速提示
    if car.boost_timer > 0:
        t_  = car.boost_timer / 3.0
        col = lerpC(C.YEL, C.BOOST, t_)
        bt  = big.render("BOOST", True, col)
        surf.blit(bt, bt.get_rect(center=(W // 2, 36)))

    # ── 操作提示（底部，半透明）
    hint = tiny.render(
        "→ 油门   ← 刹车   ↑↓ 倾斜   空格 制动   R 重开   ESC 暂停",
        True, (130, 135, 150))
    surf.blit(hint, (16, H - 22))


# ════════════════════════════ 主游戏类 ════════════════════════════
class Game:
    S_MENU         = "menu"
    S_SELECT       = "car_select"
    S_PLAYING      = "playing"
    S_MUSIC_SELECT = "music_select"

    def __init__(self):
        pygame.init()
        pygame.key.stop_text_input()  # 禁用 IME 输入法，防止中文输入干扰按键
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("车之旅")
        _icon_path = _resource_dir() / "icon.png"
        if _icon_path.exists():
            _icon = pygame.image.load(str(_icon_path))
            pygame.display.set_icon(_icon)
        self.clock  = pygame.time.Clock()
        self.font   = self._font(20)
        self.big    = self._font(34)
        self.huge   = self._font(62)
        self.tiny   = self._font(15)
        self.audio  = Audio()
        load_sprites()

        self.state     = Game.S_MENU
        self.menu_i    = 0
        self.car_i     = 0
        self.paused    = False

        # 模式
        self.game_mode = "play"   # play / pomodoro / music
        # Music 文件夹
        self.music_files   = scan_music_files()
        self.music_idx     = 0    # 当前选中的音乐索引
        self.music_sel_i   = 0    # 音乐选择界面的光标
        self._load_active_music()
        # ── 番茄钟
        self.pomo_focus   = 25      # 专注分钟数
        self.pomo_break   = 5       # 休息分钟数
        self.pomo_state   = None    # None/idle/focus/focus_done/break/break_done
        self.pomo_elapsed = 0.0
        self.pomo_round   = 0
        # 自定义音乐
        self.custom_music_path   = None
        self.custom_beat_times   = []
        self.custom_music_bpm    = 120.0
        self.custom_music_label  = ""
        self.custom_music_dur    = 180.0    # 歌曲时长（秒），用于循环检测
        self._last_music_t_raw   = 0.0      # 上一帧的 music_t（用来检测循环回头）
        self.beat_mode           = False    # 音乐卡点模式
        self.pomo_music            = False    # 番茄钟模式：是否开启背景音乐
        self._prev_state           = None     # 用于检测状态变化
        self._menu_anim_y          = 0.0      # 菜单选择框弹簧动画位置
        self._menu_vel             = 0.0      # 弹簧速度（PD控制器）
        self._preview_timer        = 0.0      # 音乐预览延迟倒计时
        self._preview_idx          = -1       # 等待预览的音乐索引
        # ── 卡点功能状态 ──
        self.beats               = []     # 节拍标记列表，每项 {"bt", "hit", "x", "y"}
        self.beat_flash          = 0.0    # 屏幕脉冲强度，命中时拉满，逐帧衰减
        self.note_particles      = []     # 音符特效粒子（命中菱形时爆发）
        self._note_font          = None   # 渲染音符用的字体（延迟初始化）
        # ── 番茄钟历史 ──
        self.pomo_log            = pomo_log_load()
        self._show_pomo_stats    = False  # 番茄钟选车界面：详细历史面板开关
        self._reset()

    def _font(self, size):
        for fn in ["Microsoft YaHei UI", "Microsoft YaHei",
                   "SimHei", "PingFang SC", "Arial Unicode MS", "Segoe UI"]:
            try:
                f = pygame.font.SysFont(fn, size)
                if f:
                    return f
            except Exception:
                pass
        return pygame.font.SysFont(None, size)

    def _resume_music(self):
        """退出游戏时恢复当前选择的音乐，无选择则播放默认 BGM"""
        try:
            pygame.mixer.music.set_volume(self.audio.music_volume)
            if self.custom_music_path:
                pygame.mixer.music.load(self.custom_music_path)
                pygame.mixer.music.play(-1)
            else:
                self.audio.start_music()
        except Exception:
            pass

    def _auto_select_car(self):
        """音乐模式：根据BPM智能选车"""
        bpm = self.custom_music_bpm
        if bpm < 90:
            self.car_i = 0   # 云游 - 慢节奏
        elif bpm < 155:
            self.car_i = 1   # 逐风 - 中速
        else:
            self.car_i = 2   # 离弦 - 快节奏

    def _load_active_music(self):
        """根据当前选中音乐更新 custom_music_path 和节拍"""        
        self.music_files = scan_music_files()
        if self.music_files and self.music_idx < len(self.music_files):
            fp = str(self.music_files[self.music_idx])
            beats, bpm, dur = analyze_music_beats(fp)
            self.custom_music_path  = fp
            self.custom_beat_times  = beats
            self.custom_music_bpm   = bpm
            self.custom_music_dur   = max(5.0, float(dur))
            self.custom_music_label = self.music_files[self.music_idx].name[:24]
        else:
            self.custom_music_path  = None
            self.custom_beat_times  = []
            self.custom_music_bpm   = 120.0
            self.custom_music_dur   = 180.0
            self.custom_music_label = ""

    def _reset(self):
        cfg  = CARS[self.car_i]
        seed = random.randint(0, 999_999)
        global GAME_SEED
        GAME_SEED      = seed
        self.terrain   = Terrain(seed=seed)
        self.parallax  = ParallaxBG(seed=seed)
        sx = 10.0
        sy = self.terrain.height(sx) + 3.0
        self.car       = Car(cfg, x=sx, y=sy)
        self.particles = Particles()
        self.camera    = Camera()
        self.camera.pos.x = sx * PPM
        self.camera.pos.y = sy * PPM
        self.start_x   = sx
        self.elapsed   = 0.0
        self._repair_timer = 0.0

        # 杂物类型表
        DEBRIS_TYPES = [
            {"kind": "crate",  "col": (185, 135, 72),  "col2": (140, 95, 45),  "r": 0.32},
            {"kind": "barrel", "col": (55,  90,  135),  "col2": (200, 75,  35),  "r": 0.28},
            {"kind": "cone",   "col": (255, 110, 25),   "col2": (255, 220, 50),  "r": 0.22},
            {"kind": "box",    "col": (218, 195, 148),  "col2": (165, 140, 95),  "r": 0.25},
            {"kind": "sign",   "col": (235, 215, 55),   "col2": (50,  50,  55),  "r": 0.20},
        ]
        self.boosts = []
        self.debris = []
        # 音乐模式不生成杂物/加速板（路面干净，菱形完美卡点）
        # 加速板：仅游玩模式生成
        if self.game_mode == "play":
            x = 100.0
            while x < 30000.0:
                self.boosts.append({
                    "x":     x + random.uniform(-10, 10),
                    "y":     self.terrain.height(x) + 0.25,
                    "taken": False,
                })
                x += random.uniform(85, 130)
        # 杂物：仅游玩模式生成
        if self.game_mode == "play":
            dx_ = 45.0
            while dx_ < 30000.0:
                cluster_n = random.randint(2, 4)
                for _ in range(cluster_n):
                    ox = dx_ + random.uniform(-2, 2)
                    oy = self.terrain.height(ox)
                    tp = random.choice(DEBRIS_TYPES)
                    self.debris.append({
                        "x":      ox,
                        "y":      oy + tp["r"],
                        "r":      tp["r"],
                        "kind":   tp["kind"],
                        "col":    tp["col"],
                        "col2":   tp["col2"],
                        "rot":    random.uniform(0, math.tau),
                        "smashed": False,
                    })
                dx_ += random.uniform(10, 18)

        # 熔岩喷发口
        self.jets = []
        for seg in range(80):
            if BIOMES[slot_biome_idx(seg)]["name"] != "VOLCANO":
                continue
            base = seg * BIOME_LEN
            for k in range(8):
                jx = base + 55 + k * 55 + random.uniform(-12, 12)
                self.jets.append({
                    "x": jx, "y": self.terrain.height(jx),
                    "period": random.uniform(2.0, 3.8),
                    "dur":    0.85,
                    "t0":     random.uniform(0, 3.5),
                })

        # ── 节拍标记：音乐模式 或 番茄钟+音乐+卡点 时生成 ──
        # B方案：只存节拍时间，位置由 _update 每帧根据 music_t + 车实时位置投影
        self.beats = []
        _beat_enabled = (
            (self.game_mode == "music" and self.beat_mode) or
            (self.game_mode == "pomodoro" and self.pomo_music and self.beat_mode)
        )
        if _beat_enabled and self.custom_beat_times:
            # 菱形保留"每拍都生成" — 玩家密集卡点的核心爽感
            # 杂物/加速板按小节生成 — 节拍器强拍层次感
            # 两者叠加：每拍踩菱形 + 每小节强拍撞杂物
            for bt in self.custom_beat_times:
                self.beats.append({
                    "bt":   float(bt),
                    "hit":  False,
                    "x":    -1e9,
                    "y":    0.0,
                    "r":    0.22,
                    "kind": "beat",
                    "col":  (255, 235, 60),
                    "col2": (255, 180, 20),
                    "rot":  0,
                    "smashed": False,
                })
        # 屏幕脉冲与音乐时间基准重置
        self.beat_flash          = 0.0
        self.note_particles      = []
        self._last_music_t_raw   = 0.0   # 循环检测重置

    # ── 主循环 ─────────────────────────────────────────────────
    def run(self):
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    return
                if ev.type == pygame.KEYDOWN:
                    self._key(ev.key)

            # ── 状态变化检测：统一管理音乐切换
            if self.state != self._prev_state:
                prev = self._prev_state
                cur  = self.state
                # 进入菜单 → 默认 BGM
                if cur == Game.S_MENU:
                    try:
                        self.audio.start_music()
                    except Exception: pass
                # 进入游戏 → 选择的音乐（若有）
                elif cur == Game.S_PLAYING:
                    try:
                        if self.custom_music_path:
                            pygame.mixer.music.load(self.custom_music_path)
                            pygame.mixer.music.set_volume(self.audio.music_volume)
                            pygame.mixer.music.play(-1)
                        else:
                            self.audio.start_music()
                    except Exception: pass
                # 进入音乐选择 → 停止当前（等待预览）
                elif cur == Game.S_MUSIC_SELECT:
                    self._preview_timer = 0.0
                    self._preview_idx   = self.music_sel_i
                self._prev_state = cur
            # ── 音乐预览倒计时
            if self.state == Game.S_MUSIC_SELECT and self._preview_timer > 0:
                self._preview_timer -= DT
                if self._preview_timer <= 0:
                    try:
                        fp = self.music_files[self._preview_idx]
                        pygame.mixer.music.load(str(fp))
                        pygame.mixer.music.set_volume(self.audio.music_volume)
                        pygame.mixer.music.play()
                    except Exception: pass
            if self.state == Game.S_MENU:
                self._draw_menu()
            elif self.state == Game.S_SELECT:
                self._draw_select()
            elif self.state == Game.S_PLAYING:
                if not self.paused:
                    self._update(DT)
                self._draw_game()
                if self.paused:
                    self._draw_pause()
            elif self.state == Game.S_MUSIC_SELECT:
                self._draw_music_select()

            pygame.display.flip()
            self.clock.tick(FPS)

    # ── 按键 ───────────────────────────────────────────────────
    def _key(self, k):
        if self.state == Game.S_MENU:
            if k == pygame.K_UP:
                self.menu_i = (self.menu_i - 1) % 5
                self.audio.play("click", 0.3)
            elif k == pygame.K_DOWN:
                self.menu_i = (self.menu_i + 1) % 5
                self.audio.play("click", 0.3)
            elif k in (pygame.K_RETURN, pygame.K_SPACE):
                if self.menu_i == 0:
                    self.game_mode = "play"
                    self.state     = Game.S_SELECT
                elif self.menu_i == 1:
                    self.game_mode = "pomodoro"
                    self.pomo_state = "idle"
                    self.state     = Game.S_SELECT
                elif self.menu_i == 2:
                    self.game_mode = "music"
                    # 不再按 BPM 自动选车，进入选车界面让玩家自由选
                    self.pomo_state = None
                    self.state     = Game.S_SELECT
                elif self.menu_i == 3:
                    self.state = Game.S_MUSIC_SELECT
                    self.music_sel_i = self.music_idx
                else:
                    pygame.quit(); sys.exit(0)
                self.audio.play("start", 0.4)
            elif k == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit(0)

        elif self.state == Game.S_SELECT:
            is_yunyu  = CARS[self.car_i]["key"] == "touring"
            max_cars  = 2 if self.game_mode == "pomodoro" else len(CARS)
            if k == pygame.K_LEFT:
                self.car_i = (self.car_i - 1) % max_cars
                self.audio.play("click", 0.3)
            elif k == pygame.K_RIGHT:
                self.car_i = (self.car_i + 1) % max_cars
                self.audio.play("click", 0.3)
            elif k == pygame.K_o and self.game_mode == "pomodoro":
                self.pomo_music = not self.pomo_music
                self.audio.play("click", 0.3)
            elif k == pygame.K_h and self.game_mode == "pomodoro":
                # 切换番茄钟历史面板
                self._show_pomo_stats = not self._show_pomo_stats
                self.audio.play("click", 0.3)
            elif k == pygame.K_LEFTBRACKET and self.game_mode == "pomodoro":
                self.pomo_focus = max(1, self.pomo_focus - 5)
            elif k == pygame.K_RIGHTBRACKET and self.game_mode == "pomodoro":
                self.pomo_focus = min(120, self.pomo_focus + 5)
            elif k == pygame.K_MINUS and self.game_mode == "pomodoro":
                self.pomo_break = max(1, self.pomo_break - 1)
            elif k == pygame.K_EQUALS and self.game_mode == "pomodoro":
                self.pomo_break = min(30, self.pomo_break + 1)
            elif k in (pygame.K_RETURN, pygame.K_SPACE):
                self._reset()
                if self.game_mode == "pomodoro":
                    self.pomo_state   = "idle"
                    self.pomo_elapsed = 0.0
                    self.pomo_round   = 0
                else:
                    self.pomo_state = None
                self.state = Game.S_PLAYING
                self.audio.play("start", 0.4)
            elif k == pygame.K_ESCAPE:
                self.state = Game.S_MENU

        elif self.state == Game.S_PLAYING:
            pomo_blocking = self.pomo_state in ("idle", "focus_done", "break_done")
            if k == pygame.K_ESCAPE:
                if pomo_blocking:
                    # ESC 在番茄钟阻塞界面 = 取消番茄钟，恢复正常
                    self.pomo_state = None
                else:
                    self.paused = not self.paused
                    if self.paused: self.audio.stop_engine()
            elif k == pygame.K_r:
                self._reset()
                self.pomo_state = None
                self.state = Game.S_PLAYING
            elif k == pygame.K_m and self.paused:
                self.state  = Game.S_MENU
                self.paused = False
            elif k == pygame.K_SPACE:
                # 番茄钟通知状态：空格进入下一阶段
                if self.pomo_state == "idle":
                    self.pomo_state   = "focus"
                    self.pomo_elapsed = 0.0
                    self.pomo_round  += 1
                elif self.pomo_state == "focus_done":
                    self.pomo_state   = "break"
                    self.pomo_elapsed = 0.0
                elif self.pomo_state == "break_done":
                    self.pomo_state   = "focus"
                    self.pomo_elapsed = 0.0
                    self.pomo_round  += 1
                # 普通模式：空格 = 刹车（在 _update 中处理按住状态）

        elif self.state == Game.S_MUSIC_SELECT:
            n = max(1, len(self.music_files))
            if k == pygame.K_UP:
                self.music_sel_i    = (self.music_sel_i - 1) % n
                self._preview_timer = 1.0
                self._preview_idx   = self.music_sel_i
            elif k == pygame.K_DOWN:
                self.music_sel_i    = (self.music_sel_i + 1) % n
                self._preview_timer = 1.0
                self._preview_idx   = self.music_sel_i
            elif k in (pygame.K_RETURN, pygame.K_SPACE):
                self.music_idx = self.music_sel_i
                self._load_active_music()
                self.audio.stop_music()
                self.state = Game.S_MENU
            elif k == pygame.K_m:
                # M：导入音乐文件到 Music 文件夹
                try:
                    import tkinter as tk, shutil
                    from tkinter import filedialog
                    root = tk.Tk(); root.withdraw()
                    root.attributes("-topmost", True)
                    fp = filedialog.askopenfilename(
                        title="导入音乐",
                        filetypes=[("音频","*.wav *.ogg *.mp3"),("所有","*.*")])
                    root.destroy()
                    if fp:
                        dest = MUSIC_DIR / Path(fp).name
                        shutil.copy2(fp, dest)
                        self.music_files = scan_music_files()
                        self.music_sel_i = next(
                            (i for i,f in enumerate(self.music_files)
                             if f == dest), 0)
                except Exception:
                    pass
            elif k == pygame.K_b:
                self.beat_mode = not self.beat_mode
                self.audio.play("click", 0.3)
            elif k == pygame.K_ESCAPE:
                self.state = Game.S_MENU

    # ── 游戏逻辑 ───────────────────────────────────────────────
    def _update(self, dt):
        self.elapsed  += dt
        self.parallax.step(dt)
        keys = pygame.key.get_pressed()
        car  = self.car

        # ── 番茄钟逻辑
        pomo_blocking = self.pomo_state in ("idle", "focus_done", "break_done")
        auto_drive = (self.pomo_state == "focus" or self.game_mode == "music")
        if auto_drive:
            if self.pomo_state == "focus":
                self.pomo_elapsed += dt
            car.brake = False
            car.tilt  = (-1.0 if keys[pygame.K_UP] else
                          1.0 if keys[pygame.K_DOWN] else 0.0)
            if self.game_mode == "music":
                # 音乐模式：匀速 60 km/h，稳定卡点
                TARGET_SPD = 60.0 / 3.6
                spd = car.chassis.vel.x
                if spd < TARGET_SPD - 1.5:
                    car.throttle = 1.0
                elif spd > TARGET_SPD + 1.5:
                    car.throttle = 0.0
                else:
                    car.throttle = 0.5
            else:
                car.throttle = 1.0   # 番茄钟普通自动前行
            if (self.pomo_state == "focus" and
                    self.pomo_elapsed >= self.pomo_focus * 60):
                self.pomo_state   = "focus_done"
                self.pomo_elapsed = 0.0
                car.throttle      = 0.0
                # 番茄钟模式提示音要更响
                vol = 1.0 if self.game_mode == "pomodoro" else 0.5
                self.audio.play("flip", vol)
                # 记录到历史日志
                pomo_log_add(self.pomo_log, self.pomo_focus, completed=True)
        elif self.pomo_state == "break":
            self.pomo_elapsed += dt
            # 休息时缓慢行驶（专注速度的 1/3，悠闲感）
            BREAK_SPD = (60.0 / 3.6) / 3.0
            spd = car.chassis.vel.x
            if spd < BREAK_SPD - 0.5:
                car.throttle = 0.4
            elif spd > BREAK_SPD + 0.5:
                car.throttle = 0.0
            else:
                car.throttle = 0.15
            car.brake    = False
            car.tilt     = (-1.0 if keys[pygame.K_UP] else
                             1.0 if keys[pygame.K_DOWN] else 0.0)
            if self.pomo_elapsed >= self.pomo_break * 60:
                self.pomo_state   = "break_done"
                self.pomo_elapsed = 0.0
                vol = 1.0 if self.game_mode == "pomodoro" else 0.5
                self.audio.play("boost", vol)
        elif not pomo_blocking:
            # 普通操控
            car.throttle = (1.0 if keys[pygame.K_RIGHT] else
                        -0.7 if keys[pygame.K_LEFT] else 0.0)
            car.brake    = keys[pygame.K_SPACE] and not pomo_blocking
            car.tilt     = (-1.0 if keys[pygame.K_UP] else
                             1.0 if keys[pygame.K_DOWN] else 0.0)

        _b0, _b1, _bt = get_biome_blend(car.chassis.pos.x)
        _grav = lerp(_b0["gravity"], _b1["gravity"], _bt)
        _fric = lerp(_b0["friction"], _b1["friction"], _bt)
        car.step(self.terrain, self.particles, grav_scale=_grav, fric_scale=_fric)
        self.particles.step(dt, grav_scale=_grav)
        # 深海：持续冒气泡
        if _b0["name"] == "DEEP_SEA" or _b1["name"] == "DEEP_SEA":
            if random.random() < 0.18:
                bx = car.chassis.pos.x + random.uniform(-10, 10)
                by = self.terrain.height(bx) + random.uniform(0.2, 4)
                self.particles.emit_bubble(pygame.Vector2(bx, by))
        self.camera.follow(car.chassis.pos, car.chassis.vel.x * PPM)
        self.camera.step(dt)

        # ── 音频控制（按模式）
        pomo_active = self.pomo_state in ("focus", "break", "focus_done", "break_done")
        if self.game_mode == "pomodoro":
            # 番茄钟模式：引擎静音，背景音乐可选
            self.audio.stop_engine()
            try:
                if self.pomo_music:
                    pygame.mixer.music.set_volume(self.audio.music_volume)
                    if not pygame.mixer.music.get_busy():
                        # 优先用用户选的音乐（这样卡点才有节拍数据）
                        if self.custom_music_path:
                            pygame.mixer.music.load(self.custom_music_path)
                            pygame.mixer.music.play(-1)
                        else:
                            self.audio.start_music()
                else:
                    pygame.mixer.music.set_volume(0)
            except Exception: pass
        elif self.game_mode == "music" or pomo_active:
            # 音乐模式 / 番茄钟专注中：停引擎，只播音乐
            self.audio.stop_engine()
            try: pygame.mixer.music.set_volume(self.audio.music_volume)
            except Exception: pass
        else:
            self.audio.update_engine(car.speed_kmh(), car.throttle)
            try: pygame.mixer.music.set_volume(self.audio.music_volume)
            except Exception: pass

        # 加速板拾取
        for b in ([] if self.game_mode == "pomodoro" else self.boosts):
            if b.get("taken"):
                continue
            if (abs(b["x"] - car.chassis.pos.x) < 1.25 and
                    abs(b["y"] - car.chassis.pos.y) < 1.05):
                b["taken"]       = True
                car.boost_timer  = 3.0
                self.camera.add_shake(6)
                self.particles.emit_boost(car.chassis.pos)
                if self.game_mode != "pomodoro":
                    self.audio.play("boost", 0.45)

        # 路面杂物：一碰就炸开，不阻挡车
        for d in self.debris:
            if d.get("smashed"):
                continue
            dx = d["x"] - car.chassis.pos.x
            dy = d["y"] - car.chassis.pos.y
            if abs(dx) > 2.5 or abs(dy) > 2.0:
                continue
            dist_ = math.hypot(dx, dy)
            if dist_ < d["r"] + car.chassis.width * 0.45:
                d["smashed"] = True
                spd = car.chassis.vel.length()
                # 杂物飞散粒子
                col = d["col"]
                for _ in range(10):
                    self.particles.emit_debris(pygame.Vector2(d["x"], d["y"]),
                                               color=col, n=1)
                self.particles.emit_spark(pygame.Vector2(d["x"], d["y"]),
                                          color=col, n=8)
                self.camera.add_shake(min(12, spd * 0.5))
                kind_ = d["kind"]
                sfx_  = "break_wood" if kind_ in ("crate","box") else "crash_metal"
                if self.game_mode != "pomodoro":
                    self.audio.play(sfx_, 0.55)

        # ── 卡点功能：B + C 方案 ──
        if self.beats:
            # 1. 获取 music_t：pygame.mixer.music.get_pos() 是从 play() 开始的总时间
            #    （即使 loops=-1 循环播放也不会重置），所以要自己模 dur 算循环内位置
            try:
                pos_ms = pygame.mixer.music.get_pos()
                music_t_raw = pos_ms / 1000.0 if pos_ms >= 0 else self.elapsed
            except Exception:
                music_t_raw = self.elapsed
            dur = max(5.0, self.custom_music_dur)
            # 检测循环回头：跨过 dur 整数倍 → 重置所有 beat 的命中状态
            prev_loop = int(self._last_music_t_raw / dur)
            this_loop = int(music_t_raw / dur)
            if this_loop > prev_loop:
                for b in self.beats:
                    b["hit"]     = False
                    b["smashed"] = False
            self._last_music_t_raw = music_t_raw
            # 实际用于比较的 music_t：循环内位置
            music_t = music_t_raw % dur
            car_x = car.chassis.pos.x
            car_v = max(2.0, car.chassis.vel.x)   # 避免除零，最低视为2m/s
            # 2. 每帧重投影未命中的 beat 位置
            for b in self.beats:
                if b["hit"]:
                    continue
                dt_to_beat = b["bt"] - music_t
                if dt_to_beat < -0.5:
                    # 已经错过 0.5 秒以上：当作未命中过期，避免阻塞遍历
                    b["hit"] = True
                    continue
                if dt_to_beat > 8.0:
                    # 距离太远，先放在视野外的远点，省得算地形高度
                    b["x"] = car_x + 800.0
                    continue
                # 投影到车前方
                wx = car_x + car_v * dt_to_beat
                b["x"] = wx
                b["y"] = self.terrain.height(wx) + 0.45
            # 3. 命中检测：车的水平距离 < 阈值 触发反馈
            HIT_DIST = 0.3   # 命中半径（米）
            for b in self.beats:
                if b["hit"]:
                    continue
                if abs(b["x"] - car_x) < HIT_DIST and abs(b["y"] - car.chassis.pos.y) < 2.0:
                    b["hit"]     = True
                    b["smashed"] = True   # 让渲染层不再画它
                    # 清脆音效
                    self.audio.play("ding", 0.5)
                    # 粒子爆炸：金黄+白色火花
                    pos = pygame.Vector2(b["x"], b["y"])
                    self.particles.emit_spark(pos, color=(255, 235, 80), n=12)
                    self.particles.emit_spark(pos, color=(255, 255, 255), n=6)
                    # ── 音符特效：从车头位置爆发 4 个音符 ──
                    note_pos_x = car.chassis.pos.x
                    note_pos_y = car.chassis.pos.y + 1.0
                    NOTE_COLS  = [(255, 235, 80), (255, 200, 120),
                                  (200, 230, 255), (255, 255, 255)]
                    for _i in range(4):
                        ang = random.uniform(-2.2, -0.9)   # 向上偏左/右
                        sp  = random.uniform(4.5, 7.5)
                        self.note_particles.append({
                            "x":    note_pos_x + random.uniform(-0.3, 0.3),
                            "y":    note_pos_y,
                            "vx":   math.cos(ang) * sp,
                            "vy":   -math.sin(ang) * sp,   # 世界坐标向上=+y
                            "life": 1.1,
                            "max":  1.1,
                            "col":  random.choice(NOTE_COLS),
                            "size": random.randint(18, 26),
                            "flag": random.choice([1, 1, 2]),   # 单旗或双旗
                            "spin": random.uniform(-3.0, 3.0),  # 旋转角速度
                            "rot":  random.uniform(-0.3, 0.3),  # 初始倾斜
                        })
                    # 屏幕脉冲
                    self.beat_flash = 1.0
                    self.camera.add_shake(2.5)
        # 屏幕脉冲衰减
        if self.beat_flash > 0:
            self.beat_flash = max(0.0, self.beat_flash - dt * 4.0)
        # ── 推进音符粒子 ──
        if self.note_particles:
            keep = []
            for n in self.note_particles:
                n["life"] -= dt
                if n["life"] <= 0:
                    continue
                n["x"]   += n["vx"] * dt
                n["y"]   += n["vy"] * dt
                n["vy"]  -= dt * 1.2     # 重力很弱（世界坐标）
                n["vx"]  *= 0.96         # 横向阻尼
                n["rot"] += n["spin"] * dt
                keep.append(n)
            self.note_particles = keep

        # 熔岩喷发粒子（不杀死玩家，只炫）
        t = self.elapsed
        for j in self.jets:
            if abs(j["x"] - car.chassis.pos.x) > 3:
                continue
            phase = (t - j["t0"]) % j["period"]
            if phase < j["dur"] and random.random() < 0.3:
                self.particles.emit_lava(pygame.Vector2(j["x"], j["y"] + 0.5))
            # 熔岩能把车弹飞但不死
            if phase < j["dur"] and abs(j["x"] - car.chassis.pos.x) < 1.5:
                if car.chassis.pos.y < j["y"] + 3.5:
                    car.chassis.vel.y += 15.0 * dt
                    self.camera.add_shake(8)
                    self.particles.emit_lava(pygame.Vector2(j["x"], j["y"] + 1))

        # 轮子/车顶飞掉后自动修复（3秒）
        if car.rear.detached or car.front.detached:
            self._repair_timer = getattr(self, "_repair_timer", 0.0) + dt
            if self._repair_timer > 3.0:
                car.rear.detached  = False
                car.front.detached = False
                car.roof_on        = True
                car.rear.vel.update(0, 0)
                car.front.vel.update(0, 0)
                self._repair_timer = 0.0
                self.particles.emit_spark(car.chassis.pos, color=C.GRN, n=20)
        else:
            self._repair_timer = 0.0

        # 落地音效：由空中转为接地时触发
        was_air  = getattr(self, '_was_in_air', False)
        now_air  = not (car.rear.grounded or car.front.grounded)
        if was_air and not now_air:
            spd_ = car.chassis.vel.length() * 3.6
            if spd_ > 30:
                if self.game_mode != "pomodoro":
                    self.audio.play("landing", min(1.0, spd_ / 120))
                self.camera.add_shake(min(10, spd_ * 0.06))
        self._was_in_air = now_air



    # ── 主画面 ─────────────────────────────────────────────────
    def _draw_game(self):
        car    = self.car
        dist_m = max(0, car.chassis.pos.x - self.start_x)
        self.parallax.draw(self.screen, self.camera, car.chassis.pos.x)
        draw_terrain(self.screen, self.terrain, self.camera)
        boosts_vis = [] if self.game_mode == "pomodoro" else self.boosts
        # 合并 debris + 节拍标记（节拍标记位置已在 _update 中投影到车前方）
        pickups_all = self.debris + self.beats if self.beats else self.debris
        draw_pickups(self.screen, self.camera, boosts_vis, pickups_all, self.elapsed)
        draw_lava_jets(self.screen, self.camera, self.jets, self.elapsed)
        car.draw(self.screen, self.camera)
        self.particles.draw(self.screen, self.camera)
        # ── 渲染音符特效（纯几何图形：椭圆头+竖茎+旗，不依赖字体）──
        if self.note_particles:
            for nt in self.note_particles:
                sx, sy = scr(nt["x"], nt["y"], self.camera)
                if not (-40 < sx < W + 40 and -40 < sy < H + 40):
                    continue
                t_ratio = nt["life"] / nt["max"]
                alpha   = max(0, min(255, int(255 * t_ratio)))
                size    = int(nt["size"] * (0.6 + 0.4 * t_ratio))
                col     = nt["col"]
                col_a   = (*col, alpha)
                # 在透明 surface 上画好再旋转贴回
                W_S   = size * 3
                H_S   = size * 3
                ns    = pygame.Surface((W_S, H_S), pygame.SRCALPHA)
                cx, cy = W_S // 2, H_S // 2
                head_w = size
                head_h = max(4, int(size * 0.7))
                # 椭圆头（中心略偏左下）
                head_x = cx - head_w // 2 - 2
                head_y = cy + size // 4 - head_h // 2
                pygame.draw.ellipse(ns, col_a, (head_x, head_y, head_w, head_h))
                # 竖茎（右上）
                stem_x = head_x + head_w - 1
                stem_top = cy - size
                pygame.draw.line(ns, col_a, (stem_x, stem_top),
                                 (stem_x, head_y + head_h // 2), 2)
                # 旗子（1 或 2 个）
                flag_n = nt.get("flag", 1)
                for fi in range(flag_n):
                    fy = stem_top + fi * 5
                    pygame.draw.line(ns, col_a, (stem_x, fy),
                                     (stem_x + max(4, size // 2), fy + 5), 2)
                # 旋转
                rot_deg = nt["rot"] * 57.2958   # 弧度→度
                ns_r = pygame.transform.rotate(ns, rot_deg)
                self.screen.blit(ns_r, ns_r.get_rect(center=(sx, sy)))
        # 卡点屏幕脉冲：四周黄光
        if self.beat_flash > 0.02:
            flash = pygame.Surface((W, H), pygame.SRCALPHA)
            alpha = int(120 * self.beat_flash)
            # 上下边缘黄光
            pygame.draw.rect(flash, (255, 235, 80, alpha), (0, 0, W, 18))
            pygame.draw.rect(flash, (255, 235, 80, alpha), (0, H - 18, W, 18))
            pygame.draw.rect(flash, (255, 235, 80, alpha), (0, 0, 18, H))
            pygame.draw.rect(flash, (255, 235, 80, alpha), (W - 18, 0, 18, H))
            self.screen.blit(flash, (0, 0))
        draw_hud(self.screen, car, dist_m, self.terrain,
                 self.font, self.big, self.huge, self.tiny)
        # 番茄钟 HUD
        if self.pomo_state:
            self._draw_pomo_hud()

    def _draw_pomo_hud(self):
        """游戏内番茄钟计时条和通知界面"""
        ps = self.pomo_state

        # ── 通知界面（阻塞状态）
        if ps in ("idle", "focus_done", "break_done"):
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 145))
            self.screen.blit(ov, (0, 0))
            pw, ph = 520, 220
            px, py = W // 2 - pw // 2, H // 2 - ph // 2
            _panel(self.screen, px, py, pw, ph, alpha=210,
                   accent=(80, 200, 130) if ps != "break_done" else (255, 180, 50))

            if ps == "idle":
                title = "准备好了吗？"
                sub   = f"专注 {self.pomo_focus} 分钟 · 休息 {self.pomo_break} 分钟"
                hint  = "按  空格  开始第一轮专注"
                col   = (80, 220, 140)
            elif ps == "focus_done":
                title = f"第 {self.pomo_round} 轮专注完成！"
                sub   = f"认真工作了 {self.pomo_focus} 分钟，休息一下吧"
                hint  = "按  空格  开始休息"
                col   = (255, 210, 80)
            else:  # break_done
                title = "休息结束，继续出发！"
                sub   = f"第 {self.pomo_round + 1} 轮专注即将开始"
                hint  = "按  空格  继续专注"
                col   = (80, 190, 255)

            t_surf = self.big.render(title, True, col)
            s_surf = self.font.render(sub, True, C.GRAY)
            h_surf = self.font.render(hint, True, C.WHITE)
            self.screen.blit(t_surf, t_surf.get_rect(center=(W // 2, py + 30)))
            self.screen.blit(s_surf, s_surf.get_rect(center=(W // 2, py + 108)))
            self.screen.blit(h_surf, h_surf.get_rect(center=(W // 2, py + 160)))
            return

        # ── 小计时面板（专注/休息进行中）
        is_focus  = (ps == "focus")
        total_s   = (self.pomo_focus if is_focus else self.pomo_break) * 60
        remain_s  = max(0, total_s - self.pomo_elapsed)
        mins, secs = int(remain_s // 60), int(remain_s % 60)
        phase_lbl  = f"专注中  第{self.pomo_round}轮" if is_focus else f"休息中  第{self.pomo_round}轮"
        timer_str  = f"{mins:02d}:{secs:02d}"
        bar_ratio  = 1.0 - remain_s / total_s
        accent     = (80, 220, 140) if is_focus else (255, 180, 50)

        # 计时面板
        _panel(self.screen, W // 2 - 145, H - 68, 290, 54, alpha=190, accent=accent)
        lbl = self.tiny.render(phase_lbl, True, (180, 185, 200))
        self.screen.blit(lbl, lbl.get_rect(center=(W // 2, H - 56)))
        tmr = self.big.render(timer_str, True, accent)
        self.screen.blit(tmr, tmr.get_rect(center=(W // 2, H - 34)))
        # 进度条
        bar_x, bar_y, bar_w, bar_h = W // 2 - 130, H - 18, 260, 4
        pygame.draw.rect(self.screen, C.DGRAY, (bar_x, bar_y, bar_w, bar_h), border_radius=2)
        fw = int(bar_w * bar_ratio)
        if fw > 0:
            pygame.draw.rect(self.screen, accent, (bar_x, bar_y, fw, bar_h), border_radius=2)

    def _draw_pause(self):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((0, 0, 5, 158))
        self.screen.blit(s, (0, 0))
        txt = self.huge.render("PAUSED", True, C.WHITE)
        self.screen.blit(txt, txt.get_rect(center=(W // 2, H // 2 - 35)))
        h2 = self.font.render("ESC 继续   R 重开   M 菜单", True, C.GRAY)
        self.screen.blit(h2, h2.get_rect(center=(W // 2, H // 2 + 40)))





    def _draw_menu(self):
        # ── 弹簧/PD 控制器更新动画位置
        target   = float(self.menu_i)
        err      = target - self._menu_anim_y
        self._menu_vel    += err * 0.28
        self._menu_vel    *= 0.52           # 阻尼
        self._menu_anim_y += self._menu_vel
        anim = self._menu_anim_y

        # ── 背景
        self.parallax.step(DT)
        self.parallax.draw(self.screen, self.camera, 0)
        py = int(H * 0.72)
        pygame.draw.rect(self.screen, BIOMES[0]["g0"], (0, py, W, H - py))
        pygame.draw.rect(self.screen, BIOMES[0]["g1"], (0, py + 20, W, H - py))

        # ── 标题
        title = self.huge.render("车之旅", True, C.WHITE)
        self.screen.blit(title, title.get_rect(center=(W // 2, 90)))
        sub = self.big.render("无尽旅途", True, C.YEL)
        self.screen.blit(sub, sub.get_rect(center=(W // 2, 148)))

        # ── 装饰小车
        cx_, cy_ = W // 2, py - 28
        pygame.draw.rect(self.screen, (210, 120, 48), (cx_ - 44, cy_ - 19, 88, 30))
        hi_ = lerpC((210, 120, 48), (255, 255, 255), 0.38)
        pygame.draw.rect(self.screen, hi_, (cx_ - 44, cy_ - 19, 88, 5))
        pygame.draw.polygon(self.screen, (172, 94, 38),
                            [(cx_ - 30, cy_ - 19), (cx_ + 16, cy_ - 19),
                             (cx_ + 24, cy_ - 38), (cx_ - 24, cy_ - 38)])
        for ox_ in (-28, 28):
            pygame.draw.circle(self.screen, (20, 20, 24), (cx_ + ox_, cy_ + 14), 14)
            pygame.draw.circle(self.screen, (85, 85, 96), (cx_ + ox_, cy_ + 14), 7)

        # ── 菜单项配置
        ITEM_COLS = [C.GRN, C.YEL, C.PINK, (150, 200, 255), C.GRAY]
        ITEM_NAMES = ["游玩模式", "番茄钟模式", "音乐模式", "背景音乐", "退出"]
        ITEM_DESCS = [
            "自由驾驶·三辆可选",
            "专注工作·安静陪伴",
            "跟着音乐·自动驰骋",
            self._music_label(),
            "",
        ]
        BASE_Y   = 230
        SPACING  = 54

        # ── 选择框（跟随动画）
        box_ci   = int(round(anim)) % len(ITEM_COLS)
        box_col  = ITEM_COLS[box_ci]
        box_y    = int(BASE_Y + anim * SPACING - 24)
        _panel(self.screen, W // 2 - 190, box_y, 380, 48,
               alpha=55, accent=box_col)
        # 发光描边
        pygame.draw.rect(self.screen, (*box_col, 120),
                         (W // 2 - 191, box_y - 1, 382, 50), 2, border_radius=10)

        # ── 各菜单项
        for i, (name, col, desc) in enumerate(zip(ITEM_NAMES, ITEM_COLS, ITEM_DESCS)):
            dist      = i - anim
            prox      = max(0.0, 1.0 - abs(dist))   # 0~1，越近越大
            push_y    = dist * 7                      # 远离选中项
            item_y    = int(BASE_Y + i * SPACING + push_y)
            txt_col   = lerpC(lerpC(C.GRAY, C.WHITE, 0.4), col, prox)

            # 近选中用 big 字体，远用 font
            if prox > 0.65:
                txt = self.big.render(name, True, C.YEL)
            elif prox > 0.25:
                txt = self.big.render(name, True, txt_col)
            else:
                txt = self.font.render(name, True, txt_col)
            self.screen.blit(txt, txt.get_rect(center=(W // 2, item_y)))

            # 说明文字已移至底部

        # 当前选中模式的说明（底部固定）
        _desc_list = ["自由驾驶·三辆可选·尽情享受", "专注工作·小车陪你专注", "跟着音乐·自动驰骋卡点", self._music_label(), ""]
        sel_desc = _desc_list[self.menu_i] if self.menu_i < len(_desc_list) else ""
        if sel_desc:
            ds = self.font.render(sel_desc, True, (190, 195, 210))
            self.screen.blit(ds, ds.get_rect(center=(W // 2, H - 48)))
        hint = self.tiny.render("上下选择   Enter确认   ESC退出", True, C.GRAY)
        self.screen.blit(hint, hint.get_rect(center=(W // 2, H - 22)))

    def _draw_music_select(self):
        """背景音乐选择界面"""
        self.parallax.draw(self.screen, self.camera, 0)
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 148))
        self.screen.blit(s, (0, 0))

        title = self.big.render("背景音乐", True, C.WHITE)
        self.screen.blit(title, title.get_rect(center=(W // 2, 52)))

        if not self.music_files:
            msg = self.font.render("Music 文件夹为空  按 M 导入音乐文件", True, C.GRAY)
            self.screen.blit(msg, msg.get_rect(center=(W // 2, H // 2)))
        else:
            n     = len(self.music_files)
            start = max(0, self.music_sel_i - 3)
            end   = min(n, start + 7)
            for i in range(start, end):
                f_    = self.music_files[i]
                sel   = (i == self.music_sel_i)
                cur   = (i == self.music_idx)
                col   = C.YEL if sel else (C.GRN if cur else C.GRAY)
                prefix = ">> " if sel else (" *  " if cur else "    ")
                name   = f_.name[:38]
                row    = self.font.render(prefix + name, True, col)
                y_row  = 100 + (i - start) * 44
                if sel:
                    _panel(self.screen, W//2 - 280, y_row - 16, 560, 36, alpha=80, accent=C.YEL)
                self.screen.blit(row, row.get_rect(center=(W // 2, y_row)))
                if sel and cur:
                    tag = self.tiny.render("当前", True, C.GRN)
                    self.screen.blit(tag, (W//2 + row.get_width()//2 + 10, y_row - 8))

        # 卡点模式开关（在此界面操作）
        bm_col = (80, 220, 140) if self.beat_mode else (160, 165, 185)
        bm_txt = self.tiny.render(
            "卡点模式 [B切换]: " + ("开启" if self.beat_mode else "关闭（仅音乐模式有效）"),
            True, bm_col)
        self.screen.blit(bm_txt, bm_txt.get_rect(center=(W // 2, H - 46)))
        hint = self.tiny.render(
            "上下选择   Enter确认   B切换卡点   M导入   ESC返回", True, C.GRAY)
        self.screen.blit(hint, hint.get_rect(center=(W // 2, H - 22)))


    def _music_label(self):
        if self.music_files and self.music_idx < len(self.music_files):
            return self.music_files[self.music_idx].name[:22]
        return "无音乐（导入到 Music 文件夹）"


    def _draw_select(self):
        self.parallax.draw(self.screen, self.camera, 0)
        pygame.draw.rect(self.screen, BIOMES[0]["g0"],
                         (0, int(H * 0.72), W, H - int(H * 0.72)))
        mode_labels = {"play": "游玩模式", "pomodoro": "番茄钟模式", "music": "音乐模式"}
        title_str = "选  择  你  的  车  |  " + mode_labels.get(self.game_mode, "")
        title = self.big.render(title_str, True, C.WHITE)
        self.screen.blit(title, title.get_rect(center=(W // 2, 55)))
        cars_to_show = CARS[:2] if self.game_mode == "pomodoro" else CARS
        n_cars = len(cars_to_show)
        for i, cfg in enumerate(cars_to_show):
            # 居中布局：2辆车用 W//3 间距，3辆车用 W//4 间距
            cx_ = W * (i + 1) // (n_cars + 1)
            cy_ = H // 2 - 30
            sel = (i == self.car_i)
            if sel:
                glow_s = pygame.Surface((285, 340), pygame.SRCALPHA)
                pygame.draw.rect(glow_s, (*C.YEL, 16), (0, 0, 285, 340), border_radius=12)
                self.screen.blit(glow_s, (cx_ - 142, cy_ - 112))
                pygame.draw.rect(self.screen, C.YEL,
                                 (cx_ - 140, cy_ - 110, 280, 338), 2, border_radius=12)
            self._draw_select_car(cx_, cy_ - 22, cfg)
            lbl_col  = C.YEL if sel else C.WHITE
            lbl_surf = self.big.render(cfg["label"], True, lbl_col)
            self.screen.blit(lbl_surf, lbl_surf.get_rect(center=(cx_, cy_ + 74)))

            def bar(yb, lbl_, ratio_, col_, _cx=cx_):
                self.screen.blit(self.tiny.render(lbl_, True, C.GRAY), (_cx - 95, yb))
                pygame.draw.rect(self.screen, C.DGRAY, (_cx - 38, yb + 2, 120, 11), border_radius=3)
                wf = int(120 * min(1.0, ratio_))
                if wf > 0:
                    pygame.draw.rect(self.screen, col_, (_cx - 38, yb + 2, wf, 11), border_radius=3)

            bar(cy_ + 100, "马力", cfg["engine"] / 5500, C.GRN)
            bar(cy_ + 118, "重量", cfg["mass"] / 450, C.BLU)
            bar(cy_ + 136, "限速", min(1.0, cfg.get("max_speed_kmh", 240) / 240), C.YEL)
            desc_s = self.tiny.render(cfg.get("desc", ""), True, (200, 200, 215))
            self.screen.blit(desc_s, desc_s.get_rect(center=(cx_, cy_ + 162)))


        # ── 番茄钟模式：底部双列两行面板
        if self.game_mode == "pomodoro":
            _panel(self.screen, W // 2 - 290, H - 72, 580, 48,
                   alpha=210, accent=(80, 220, 140))
            lx, rx = W // 2 - 120, W // 2 + 120
            # 行1：标签 + 数值
            foc_txt = self.font.render(f"专注: {self.pomo_focus} 分", True, C.WHITE)
            brk_txt = self.font.render(f"休息: {self.pomo_break} 分", True, C.WHITE)
            self.screen.blit(foc_txt, foc_txt.get_rect(center=(lx, H - 70)))
            self.screen.blit(brk_txt, brk_txt.get_rect(center=(rx, H - 70)))
            # 行2：按键提示
            foc_h = self.font.render("[ ]  调节专注时间", True, (130, 200, 155))
            brk_h = self.font.render("-=  调节休息时间", True, (130, 200, 155))
            self.screen.blit(foc_h, foc_h.get_rect(center=(lx, H - 45)))
            self.screen.blit(brk_h, brk_h.get_rect(center=(rx, H - 45)))
            # 分隔线
            pygame.draw.line(self.screen, (70, 90, 70), (W // 2, H - 68), (W // 2, H - 28), 1)
            # 音乐状态（上方独立显示）
            mc  = (80, 220, 140) if self.pomo_music else (130, 135, 145)
            music_text = "背景音乐: ON  (按 O 切换)" if self.pomo_music else "背景音乐: OFF  (按 O 切换)"
            mst = self.tiny.render(music_text, True, mc)
            self.screen.blit(mst, (W // 2 + 100, H - 100))
            # ── 番茄钟统计概览（一行简要）──
            st = pomo_log_stats(self.pomo_log)
            stat_text = (f"今日 {st['today_count']} 🍅  ·  "
                         f"本周 {st['week_count']} 个 / {st['week_min']} 分  ·  "
                         f"连续打卡 {st['streak']} 天   [按 H 查看历史]")
            # 去掉 emoji 避免方框
            stat_text = stat_text.replace("🍅", "个")
            st_surf = self.tiny.render(stat_text, True, (190, 200, 215))
            self.screen.blit(st_surf, st_surf.get_rect(center=(W // 2, 22)))
            # 卡点状态（只读显示）：仅在番茄钟开启音乐时显示
            if self.pomo_music:
                if self.beat_mode:
                    # 同时满足两个条件 → 卡点会启用
                    bc = (255, 220, 80)
                    beat_text = "卡点: ON  ✓"
                else:
                    bc = (130, 135, 145)
                    beat_text = "卡点: OFF  (在「背景音乐」里按 B 开启)"
                bst = self.tiny.render(beat_text, True, bc)
                self.screen.blit(bst, (W // 2 - 290, H - 100))
                # 卡点 ON 但没选音乐 → 提示
                if self.beat_mode and not self.custom_music_path:
                    warn = self.tiny.render(
                        "[!] 请先在「背景音乐」选择一首音乐",
                        True, (255, 160, 100))
                    self.screen.blit(warn, (W // 2 - 290, H - 120))

        # 已导入音乐提示
        if self.custom_music_label and self.game_mode != "pomodoro":
            ml_str = "已选音乐: %s  BPM~%d" % (
                self.custom_music_label, int(self.custom_music_bpm))
            ml = self.tiny.render(ml_str, True, (150, 165, 185))
            self.screen.blit(ml, ml.get_rect(center=(W // 2, H - 48)))
        hint_str = "左右切换   Enter出发   ESC返回"

        if self.game_mode != "pomodoro":
            hint = self.font.render(hint_str, True, C.GRAY)
            self.screen.blit(hint, hint.get_rect(center=(W // 2, H - 28)))

        # ── 番茄钟详细历史面板（叠加）──
        if self.game_mode == "pomodoro" and self._show_pomo_stats:
            self._draw_pomo_stats_panel()

    def _draw_pomo_stats_panel(self):
        """番茄钟详细历史面板（叠加层）"""
        st = pomo_log_stats(self.pomo_log)
        # 半透明背景
        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((0, 0, 5, 180))
        self.screen.blit(bg, (0, 0))
        # 主面板
        pw, ph = 640, 440
        px, py = W // 2 - pw // 2, H // 2 - ph // 2
        _panel(self.screen, px, py, pw, ph, alpha=230, accent=(80, 220, 140))
        # 标题
        ttl = self.big.render("番茄钟·专注日志", True, (80, 220, 140))
        self.screen.blit(ttl, ttl.get_rect(center=(W // 2, py + 38)))
        # 大数字统计区（4 个卡片）
        cards = [
            ("今日完成",     f"{st['today_count']}",  f"{st['today_min']} 分钟",  (255, 220, 80)),
            ("本周完成",     f"{st['week_count']}",   f"{st['week_min']} 分钟",   (140, 220, 255)),
            ("累计完成",     f"{st['total_count']}",  f"{st['total_min']} 分钟",  (200, 180, 255)),
            ("连续打卡",     f"{st['streak']}",       "天",                       (255, 180, 100)),
        ]
        card_w = 130
        card_gap = 18
        total_w = card_w * 4 + card_gap * 3
        start_x = W // 2 - total_w // 2
        cy_card = py + 100
        for i, (lbl, big_val, sub, col) in enumerate(cards):
            cx_card = start_x + i * (card_w + card_gap)
            _panel(self.screen, cx_card, cy_card, card_w, 110, alpha=140, accent=col)
            lbl_s = self.tiny.render(lbl, True, (200, 200, 215))
            self.screen.blit(lbl_s, lbl_s.get_rect(center=(cx_card + card_w // 2, cy_card + 18)))
            val_s = self.huge.render(big_val, True, col)
            self.screen.blit(val_s, val_s.get_rect(center=(cx_card + card_w // 2, cy_card + 58)))
            sub_s = self.tiny.render(sub, True, (170, 175, 190))
            self.screen.blit(sub_s, sub_s.get_rect(center=(cx_card + card_w // 2, cy_card + 92)))
        # 最近 7 次记录
        sub_ttl = self.font.render("最近记录", True, (200, 205, 215))
        self.screen.blit(sub_ttl, sub_ttl.get_rect(center=(W // 2, cy_card + 138)))
        recent = list(reversed(self.pomo_log.get("sessions", [])))[:7]
        if not recent:
            no_data = self.font.render("还没有记录，去专注一次吧", True, (150, 155, 170))
            self.screen.blit(no_data, no_data.get_rect(center=(W // 2, cy_card + 200)))
        else:
            list_y = cy_card + 168
            for i, s in enumerate(recent):
                ok_col = (80, 220, 140) if s.get("completed") else (200, 80, 80)
                ok_tag = "✓" if s.get("completed") else "x"
                ok_tag = ok_tag.replace("✓", "[OK]").replace("x", "[--]")
                line = f"{ok_tag}   {s.get('date','?')}   {s.get('start','?')}   {s.get('minutes',0)} 分钟"
                line_s = self.tiny.render(line, True, ok_col)
                self.screen.blit(line_s, line_s.get_rect(center=(W // 2, list_y + i * 22)))
        # 关闭提示
        close_s = self.tiny.render("按 H 关闭", True, (170, 175, 190))
        self.screen.blit(close_s, close_s.get_rect(center=(W // 2, py + ph - 22)))

    def _draw_select_car(self, cx_, cy_, cfg):
        w_, h_ = 98, 35
        pygame.draw.rect(self.screen, cfg["body"], (cx_ - w_ // 2, cy_ - h_ // 2, w_, h_))
        hi_ = lerpC(cfg["body"], (255, 255, 255), 0.38)
        pygame.draw.rect(self.screen, hi_, (cx_ - w_ // 2, cy_ - h_ // 2, w_, 5))
        pygame.draw.polygon(self.screen, cfg["roof"],
                            [(cx_ - w_ // 2 + 16, cy_ - h_ // 2),
                             (cx_ + w_ // 4, cy_ - h_ // 2),
                             (cx_ + w_ // 4 + 11, cy_ - h_ // 2 - 24),
                             (cx_ - w_ // 2 + 26, cy_ - h_ // 2 - 24)])
        pygame.draw.polygon(self.screen, cfg["glass"],
                            [(cx_ - w_ // 2 + 20, cy_ - h_ // 2 - 2),
                             (cx_ + w_ // 4 - 2,  cy_ - h_ // 2 - 2),
                             (cx_ + w_ // 4 + 9,  cy_ - h_ // 2 - 21),
                             (cx_ - w_ // 2 + 28, cy_ - h_ // 2 - 21)])
        for ox_ in (-30, 30):
            pygame.draw.circle(self.screen, (20, 20, 24), (cx_ + ox_, cy_ + h_ // 2 + 9), 14)
            pygame.draw.circle(self.screen, (85, 85, 96), (cx_ + ox_, cy_ + h_ // 2 + 9), 7)
        pygame.draw.rect(self.screen, cfg["accent"],
                         (cx_ - w_ // 2, cy_ - h_ // 2, w_, h_), 2)


# 入口
if __name__ == "__main__":
    Game().run()
