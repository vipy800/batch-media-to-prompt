"""配置、路径与内置预设"""
import json
import os
import sys
import threading

FROZEN = getattr(sys, "frozen", False)
_SAVE_LOCK = threading.RLock()

# 可执行文件/源码所在目录：用户数据（config.json、输出、数据库）放在这里，便于便携分发
if FROZEN:
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)  # 打包后的只读资源目录
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = BASE_DIR

APP_DIR = os.path.join(RES_DIR, "webapp")
TEMPLATE_DIR = os.path.join(APP_DIR, "templates")
STATIC_DIR = os.path.join(APP_DIR, "static")

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "输出")
THUMB_DIR = os.path.join(UPLOAD_DIR, "thumbs")
DB_PATH = os.path.join(BASE_DIR, "results.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".gif")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v")

MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 单文件 500MB
UPLOAD_EXPIRY_HOURS = 48

STANDARD_PROMPT = """你是一名资深视觉内容分析师。请仔细观察输入的画面，输出一段可直接用于 AI 生成的高质量提示词。

要求：
1. 先分模块描述：画面主体、人物/角色特征、服装与材质、姿态动作、环境场景、光影氛围、镜头与构图、色彩风格。
2. 用自然流畅的描述性语言，不要输出 JSON、不要编号标题、不要解释过程，最终只给一段可复制的提示词。
3. 保留可复现的关键细节：主体数量、方位关系、材质质感、光线方向、景别与视角、色调倾向。
4. 如画面中存在文字，用「“原文”」标注，不翻译、不臆测。
5. 只描述画面中真实存在的元素，不要虚构，也不要输出评价性、营销性废话。"""

ENGLISH_PROMPT = """You are a professional prompt engineer. Analyze the image and output ONE English prompt ready for image generation models (Stable Diffusion / Midjourney / FLUX).

Rules:
1. Describe subject, character details, clothing and fabric, pose, environment, lighting, camera angle and framing, color palette and style.
2. Use comma-separated descriptive phrases, no JSON, no headings, no explanations.
3. Keep details that are necessary to reproduce the image: object count, spatial relations, material texture, light direction, shot size, view angle.
4. If text appears in the image, wrap it in quotes, do not translate.
5. Only describe what is actually visible; never invent content.
6. Output the prompt only."""

VIDEO_PROMPT = """你是一名短视频内容分析师。请按时间顺序分析这段视频（输入为按时间均匀抽取的关键帧），输出：
1. 视频主题与整体内容概述；
2. 分阶段画面描述（每阶段一行，注明大致时间段与画面变化）；
3. 运镜与剪辑特征（景别变化、镜头运动、转场节奏）；
4. 光影、色调与氛围；
5. 可复用的分镜提示词（按阶段列出，可直接用于 AI 视频生成）。
用自然语言输出，不要 JSON，不要解释分析过程。"""

STYLE_PROMPT = """请分析这张画面的视觉风格，输出：
1. 风格流派（写实摄影 / 3D 渲染 / 二次元 / 国风 / 赛博朋克 / 油画 / 水彩 等）；
2. 色彩方案（主色、辅色、对比关系、色温）；
3. 光影与质感（光源类型、方向、软硬、材质表现）；
4. 构图与镜头语言；
5. 一段可直接复用的风格提示词（中英各一句）。
自然语言输出，不要 JSON。"""

QUALITY_PROMPT = """请对这张画面做质检分析，输出：
1. 画面类型与用途判断；
2. 清晰度、噪点、压缩痕迹、畸变等画质问题；
3. 是否存在水印、二维码、马赛克、遮挡等干扰元素（逐条列出）；
4. 构图与主体完整性问题；
5. 综合评分（0-100）与改进建议。
自然语言输出，不要 JSON。"""

VIDEO_SCRIPT_PROMPT = """你是短视频编导。按时间顺序分析这些关键帧（同一段视频均匀抽帧），输出一份可直接执行的带货/种草脚本：
1) 0-3s 钩子：画面 + 口播文案（给 2 个备选）；
2) 3-8s 产品/主体展示：景别、动作、字幕；
3) 8-15s 卖点证明：特写哪个细节、配什么文案；
4) 15-25s 使用场景：人物与环境；
5) 结尾行动号召：画面 + 一句话。
最后补 5 个可替换的钩子开头。不要 JSON，不要分析过程。"""

VIDEO_GEN_PROMPT = """你要把这段视频转成 AI 视频生成提示词。按镜头拆分，每个镜头输出一行，格式：
景别 + 主体动作 + 环境 + 运镜（推/拉/摇/移/跟/升降/手持）+ 光线 + 时长感。
最后给一段整体风格统一提示词，包含画质、色调、颗粒/锐度、帧率感与氛围。
只输出可直接复制的提示词，不要解释。"""

VIDEO_CAMERA_PROMPT = """你是摄影指导。分析这段视频的运镜与剪辑：
1) 镜头清单：按时间段列出景别、机位角度、运动方式、运动速度；
2) 转场方式与节奏点（哪一秒切、切给谁）；
3) 主体调度与焦点变化；
4) 光线与色温变化；
5) 一段可复刻同款运镜的提示词 + 分镜表。
自然语言输出，不要 JSON。"""

PORTRAIT_PROMPT = """你是资深人像摄影师兼提示词工程师。分析这张人像照片，输出一段可直接复现的中文提示词，按顺序覆盖：
1) 人物：年龄段、性别、脸型与五官特征、肤色肤质、表情与情绪；
2) 妆造：妆容重点、发型长度/颜色/卷度/刘海、发饰；
3) 服装：款式、版型、颜色、面料质感、配饰与鞋履；
4) 姿态：站/坐/行走、重心、四肢位置、手部动作、头部朝向；
5) 镜头：景别（全身/七分身/半身/特写）、机位高度、焦段感、景深；
6) 光线：光源类型与方向、软硬、明暗比、反光与阴影；
7) 环境与色调：场景元素、背景层次、色温与调色风格。
只输出提示词正文，不解释、不编号、不评价。"""

FULLBODY_PROMPT = """你是姿态复刻专家。分析这张全身照，输出能复现同款人物与姿势的提示词：
1) 体态比例：身高感、肩宽、腿长比例、站姿重心；
2) 精确姿势：双脚位置与间距、膝盖朝向、髋部角度、躯干扭转、双肩高低、手臂弯曲角度与手部位置、头部转向与下巴角度；
3) 服装逐件：长度、松紧、材质、图案、配饰；
4) 机位与透视：相机高度（平视/略低/略高）、距离感、焦距、全身是否切脚；
5) 光线与背景；
6) 画质与风格关键词（写实摄影、清晰锐利、自然皮肤质感）。
要求可直接用于生成同姿势全身图；只输出提示词正文。"""

FASHION_PROMPT = """你是服装造型分析师。拆解这张图的穿搭并输出可复用提示词：
品类清单、版型与剪裁、面料与纹理、颜色与配色关系、层次叠穿、配饰鞋包、
风格定位（通勤/街头/甜美/机能/复古等）、适合场景与季节。
最后给一段可直接用于生成同款穿搭的提示词。自然语言，不要编号标题。"""

BEAUTY_PROMPT = """你是妆造师。分析图中妆容与发型：
底妆质感与遮瑕重点、眉形、眼妆（眼线/眼影/睫毛/美瞳）、腮红与修容位置、
唇色与质地、发型结构（分区/卷度/刘海/发色/定型）、发饰。
输出一段可直接生成同款妆造的提示词，末尾附 3 个关键妆造关键词。"""

PRODUCT_PROMPT = """你是商业产品摄影师。分析这张产品图，输出电商可用的生成提示词：
产品品类与形态、材质与表面工艺（哑光/金属/玻璃/织物）、颜色与配色、
结构细节与零件、logo 与文字位置、拍摄角度（正/侧/45°）、
布光（主光/辅光/轮廓光/柔光箱）、背景与道具、构图留白、整体质感关键词。
只输出提示词正文。"""

PACKSHOT_PROMPT = """你要生成一张白底电商主图。分析产品后输出提示词，必须包含：
产品居中或黄金分割构图、纯白或浅灰无缝背景、无杂物无投影、
柔光均匀无高光死白、材质细节清晰、边缘干净、比例真实、锐度要求。
再给 3 个卖点级细节描述（材质/工艺/功能）。只输出提示词与这 3 条。"""

FOOD_PROMPT = """你是美食摄影师。分析这张美食图并输出提示词：
菜品名称与构成、摆盘方式与器皿、食材质感（酥脆/流心/油润/汁水）、
热气与动态、配色、桌面与背景、光线方向与色温（暖调侧逆光）、
景深与特写程度、氛围（家常/餐厅/野餐）。只输出提示词正文。"""

ARCH_PROMPT = """你是建筑摄影师。分析这张建筑照片并输出提示词：
建筑类型与风格、体量与层数、立面材质与纹理、结构元素（柱/窗/檐/幕墙）、
透视与消失点、机位高度与焦段、天气与时间、天空与周边环境、光影关系、色调。
只输出可直接生成同款建筑画面的提示词。"""

INTERIOR_PROMPT = """你是室内设计师。分析这张室内图：空间类型与功能、布局与动线、
墙面/地面/顶面材质与颜色、家具款式与摆放、软装（窗帘/地毯/挂画/绿植/灯具）、
照明层次（主灯/氛围灯/自然光）、风格（现代/侘寂/北欧/新中式等）、色调与质感。
输出一段生成同款空间的提示词。"""

ANIME_PROMPT = """你是二次元插画提示词专家。分析这张图，输出两部分：
A. 英文 tag 串（Danbooru 风格，逗号分隔）：人数/性别、发色发型、瞳色、表情、
服装与配饰、姿势与手势、构图景别、背景、画风（赛璐璐/厚涂/水彩）、光效、画质 tag；
B. 一句中文概述。只输出 A、B 两部分内容，不要别的文字。"""

GAME3D_PROMPT = """你是 3D/游戏美术。分析画面并输出提示词：
建模风格（写实 PBR / 卡通渲染 / 低多边形）、材质与粗糙度金属度表现、
灯光布置（三点光/环境光/轮廓光）、镜头与焦距、场景构成、配色、
渲染器质感关键词（Octane / Unreal / Blender Cycles）。只输出提示词正文。"""

FLAT_PROMPT = """你是扁平插画/矢量设计师。分析这张图：
几何构成、图形简化程度、线条粗细与圆角、配色数量与主辅色、渐变与噪点、
留白比例、图标化特征、适用场景（APP 图标/网页插画/海报）。
输出可直接生成同款扁平插画的提示词。"""

CINEMATIC_PROMPT = """你是电影摄影指导。分析这一帧：
景别与构图（三分/中心/对称）、机位与运动感、镜头特性（广角畸变/长焦压缩/变形宽银幕）、
景深、布光方案、色温与调色（青橙/低饱和/高对比）、胶片颗粒与质感、情绪基调。
输出一段带电影感的生成提示词，并附 5 个风格关键词。"""

LIGHTING_PROMPT = """你是灯光师。分析这张图的光：
主光位置与高度、光质软硬、光比、辅光与补光、轮廓光/发丝光、背景光、
色温与色偏、阴影形状与边缘、反光材质表现、时间感（清晨/正午/黄昏/夜）。
输出一段描述布光的提示词，供复现同款光影。"""

FILM_PROMPT = """分析这张照片的胶片质感：
胶片型号倾向（柯达/富士/黑白）、颗粒粗细、对比与宽容度、高光滚降、
暗部色偏、色彩偏移（青/洋红）、褪色感、暗角与漏光。
输出一段可复现该胶片风格的提示词。"""

POSTER_PROMPT = """你是平面设计师。分析这张海报：
版式结构（网格/对齐/留白）、主视觉位置、标题与副标题层级、
字体气质（黑体/宋体/手写/无衬线）、字号对比、配色方案与强调色、
装饰元素、图片与文字占比、视觉动线。
输出一段可生成同款版式的提示词，并把画面中所有文字抄录一遍（用“原文”标注，不翻译）。"""

LOGO_PROMPT = """你是品牌视觉设计师。分析这个 Logo/图标：
图形构成（几何/字母/具象）、负空间运用、线条与圆角、配色与渐变、
质感（扁平/微立体/描边）、比例与安全边距、风格气质、适用行业。
输出一段可生成同款 Logo 的提示词，并给 2 个变体方向。"""

OCR_PROMPT = """请提取这张图里的所有文字与版式信息：
按阅读顺序逐行抄录原文（保留标点与换行），标注每块文字的位置（上/中/下、左/中/右）、
字号层级（主标题/副标题/正文/角标）、字体风格与颜色。
不要翻译、不要改写、不要总结。最后用一句话说明整体版式类型。"""

UPSCALE_PROMPT = """你是图像修复与超分专家。分析这张图，输出用于「高清放大 / 修复」的提示词：
1) 主体与关键细节（发丝、皮肤纹理、织物纹理、文字边缘）；
2) 当前缺陷（模糊、噪点、压缩块、锯齿、过锐光晕）；
3) 放大时应保留的细节与应抑制的伪影；
4) 提示词正文（强调真实材质、自然皮肤、清晰边缘、无塑料感）；
5) 建议放大倍数与降噪强度区间。自然语言输出。"""

CONCISE_PROMPT = """请用一句话（不超过 60 字）概括这张图最关键的可复现要素：主体 + 动作/状态 + 场景 + 风格。只输出这一句，不要解释。"""

DETAIL_PROMPT = """请对这张图做超细粒度描述，输出一段 300-500 字的提示词，覆盖：
主体与数量、外观细节、材质纹理、颜色（具体色名与明度）、空间关系、姿态动作、
光影（方向/软硬/色温）、镜头（景别/视角/焦段）、背景层次、整体风格。
只输出描述正文，不分点、不评价。"""

NEGATIVE_PROMPT = """你是提示词工程师。针对这张图，输出一组英文 negative prompt（反向提示词），
用于避免生成时的常见瑕疵：low quality, blurry, deformed, extra limbs, bad anatomy,
watermark, text, oversharpened, plastic skin, cluttered background 等。
用逗号分隔的 tag 串，只输出这一行。"""

BUILTIN_PRESETS = [
    {"id": "standard", "name": "标准反推（中文）", "kind": "image", "group": "通用", "text": STANDARD_PROMPT},
    {"id": "english", "name": "英文提示词（SD/MJ/FLUX）", "kind": "image", "group": "通用", "text": ENGLISH_PROMPT},
    {"id": "detail", "name": "细节长描述（300-500 字）", "kind": "image", "group": "通用", "text": DETAIL_PROMPT},
    {"id": "concise", "name": "极简一句（60 字）", "kind": "image", "group": "通用", "text": CONCISE_PROMPT},
    {"id": "negative", "name": "反向提示词（负面词）", "kind": "image", "group": "通用", "text": NEGATIVE_PROMPT},

    {"id": "portrait", "name": "人像摄影（可直接出图）", "kind": "image", "group": "人像 / 服饰", "text": PORTRAIT_PROMPT},
    {"id": "fullbody", "name": "全身照 · 姿势复刻", "kind": "image", "group": "人像 / 服饰", "text": FULLBODY_PROMPT},
    {"id": "fashion", "name": "服装穿搭拆解", "kind": "image", "group": "人像 / 服饰", "text": FASHION_PROMPT},
    {"id": "beauty", "name": "妆容发型", "kind": "image", "group": "人像 / 服饰", "text": BEAUTY_PROMPT},

    {"id": "product", "name": "电商产品图", "kind": "image", "group": "电商 / 产品", "text": PRODUCT_PROMPT},
    {"id": "packshot", "name": "白底主图（Packshot）", "kind": "image", "group": "电商 / 产品", "text": PACKSHOT_PROMPT},
    {"id": "food", "name": "美食摄影", "kind": "image", "group": "电商 / 产品", "text": FOOD_PROMPT},

    {"id": "architecture", "name": "建筑外观", "kind": "image", "group": "空间 / 建筑", "text": ARCH_PROMPT},
    {"id": "interior", "name": "室内设计", "kind": "image", "group": "空间 / 建筑", "text": INTERIOR_PROMPT},

    {"id": "anime", "name": "二次元 / 动漫插画", "kind": "image", "group": "插画 / 游戏", "text": ANIME_PROMPT},
    {"id": "game3d", "name": "3D / 游戏美术", "kind": "image", "group": "插画 / 游戏", "text": GAME3D_PROMPT},
    {"id": "flat", "name": "扁平插画 / 矢量", "kind": "image", "group": "插画 / 游戏", "text": FLAT_PROMPT},

    {"id": "style", "name": "风格解析（含中英风格句）", "kind": "image", "group": "影像 / 风格", "text": STYLE_PROMPT},
    {"id": "cinematic", "name": "电影感镜头", "kind": "image", "group": "影像 / 风格", "text": CINEMATIC_PROMPT},
    {"id": "lighting", "name": "光影与布光", "kind": "image", "group": "影像 / 风格", "text": LIGHTING_PROMPT},
    {"id": "film", "name": "胶片质感", "kind": "image", "group": "影像 / 风格", "text": FILM_PROMPT},

    {"id": "poster", "name": "海报排版（含文字抄录）", "kind": "image", "group": "平面 / 文字", "text": POSTER_PROMPT},
    {"id": "logo", "name": "Logo / 图标", "kind": "image", "group": "平面 / 文字", "text": LOGO_PROMPT},
    {"id": "ocr", "name": "文字提取（OCR 式）", "kind": "image", "group": "平面 / 文字", "text": OCR_PROMPT},

    {"id": "quality", "name": "画质质检（评分+建议）", "kind": "image", "group": "质检 / 修复", "text": QUALITY_PROMPT},
    {"id": "upscale", "name": "高清放大 / 修复参考", "kind": "image", "group": "质检 / 修复", "text": UPSCALE_PROMPT},

    {"id": "video", "name": "视频分镜分析", "kind": "video", "group": "视频", "text": VIDEO_PROMPT},
    {"id": "video_script", "name": "短视频带货脚本", "kind": "video", "group": "视频", "text": VIDEO_SCRIPT_PROMPT},
    {"id": "video_prompt", "name": "视频生成提示词（按镜头）", "kind": "video", "group": "视频", "text": VIDEO_GEN_PROMPT},
    {"id": "video_camera", "name": "运镜复刻 / 分镜表", "kind": "video", "group": "视频", "text": VIDEO_CAMERA_PROMPT},
]

MODEL_SUGGESTIONS = [
    "Qwen/Qwen3-VL-32B-Instruct",
    "Qwen/Qwen2.5-VL-72B-Instruct",
    "Qwen/Qwen2.5-VL-32B-Instruct",
    "Pro/Qwen/Qwen2.5-VL-7B-Instruct",
    "deepseek-ai/deepseek-vl2",
]

DEFAULTS = {
    "api_key": os.getenv("SILICONFLOW_API_KEY", ""),
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "Qwen/Qwen3-VL-32B-Instruct",
    "video_model": "Qwen/Qwen3-VL-32B-Instruct",
    "temperature": 0.3,
    "max_tokens": 4096,
    "timeout": 600,
    "max_retries": 3,
    "concurrency": 3,
    "image_max_side": 1600,
    "jpeg_quality": 88,
    "video_frames": 9,
    "video_max_side": 1024,
    "video_grid": True,
    "output_folder": "",
    "save_next_to_source": False,
    "skip_existing": False,
    "system_prompt": "你是专业的多模态分析助手。多张图片按顺序视为同一段视频的关键帧。",
    "active_preset_image": "standard",
    "active_preset_video": "video",
    "theme": "dark",
    "custom_presets": [],
    "model_cache": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        out[k] = v
    return out


def _as_int(value, default, lo, hi):
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _as_float(value, default, lo, hi):
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _as_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes")
    return default


NUMERIC_RULES = {
    "image_max_side": (1600, 512, 4096),
    "jpeg_quality": (88, 50, 95),
    "video_frames": (9, 3, 24),
    "video_max_side": (1024, 512, 2048),
    "concurrency": (3, 1, 8),
    "timeout": (600, 10, 7200),
    "max_retries": (3, 1, 8),
    "max_tokens": (4096, 64, 16384),
}


def _normalise(cfg: dict) -> dict:
    """把磁盘/前端可能写坏的值拉回安全范围，避免任务线程因脏配置崩溃"""
    for key, (default, lo, hi) in NUMERIC_RULES.items():
        cfg[key] = _as_int(cfg.get(key, default), default, lo, hi)
    cfg["temperature"] = _as_float(cfg.get("temperature", 0.3), 0.3, 0, 2)
    cfg["video_grid"] = _as_bool(cfg.get("video_grid", True), True)
    cfg["save_next_to_source"] = _as_bool(cfg.get("save_next_to_source", False), False)
    cfg["skip_existing"] = _as_bool(cfg.get("skip_existing", False), False)
    cfg["api_key"] = str(cfg.get("api_key") or "").strip()
    cfg["base_url"] = str(cfg.get("base_url") or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if cfg["base_url"].lower().endswith(suffix):
            cfg["base_url"] = cfg["base_url"][: -len(suffix)].rstrip("/")
    for key in ("model", "video_model", "active_preset_image", "active_preset_video", "output_folder"):
        val = cfg.get(key)
        cfg[key] = "" if val is None else str(val).strip()
    cfg["theme"] = "light" if str(cfg.get("theme") or "").lower() == "light" else "dark"
    if not isinstance(cfg.get("custom_presets"), list):
        cfg["custom_presets"] = []
    if not isinstance(cfg.get("model_cache"), dict):
        cfg["model_cache"] = {}
    return cfg


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = _deep_merge(cfg, json.load(f))
        except Exception:
            pass
    return _normalise(cfg)


def save_config(patch: dict) -> dict:
    with _SAVE_LOCK:
        cfg = load_config()
        cfg.update(patch or {})
        cfg = _normalise(cfg)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
        return cfg


def all_presets() -> list:
    cfg = load_config()
    custom = cfg.get("custom_presets") or []
    out = [dict(p, builtin=True) for p in BUILTIN_PRESETS]
    for p in custom:
        q = dict(p, builtin=False)
        q.setdefault("group", "我的预设")
        out.append(q)
    return out


def get_preset(preset_id: str, kind: str = "image") -> dict:
    for p in all_presets():
        if p.get("id") == preset_id:
            return p
    for p in BUILTIN_PRESETS:
        if p.get("kind") == kind:
            return dict(p)
    return dict(BUILTIN_PRESETS[0])


def ensure_dirs():
    for d in (UPLOAD_DIR, THUMB_DIR, OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)


def output_root() -> str:
    cfg = load_config()
    folder = (cfg.get("output_folder") or "").strip()
    if not folder:
        return OUTPUT_DIR
    folder = os.path.abspath(os.path.expanduser(folder))
    return folder
