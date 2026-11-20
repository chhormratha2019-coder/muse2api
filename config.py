"""muse2api 配置。"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

_DEFAULT_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _clean_env_value(raw: str) -> str:
    """解析 .env 的值：支持引号包裹，并去掉未加引号值末尾的 ` # 行内注释`。"""
    v = raw.strip()
    if len(v) >= 2 and v[0] in ("'", '"') and v.find(v[0], 1) > 0:
        return v[1:v.find(v[0], 1)]
    for marker in (" #", "\t#"):
        idx = v.find(marker)
        if idx >= 0:
            v = v[:idx]
    return v.strip()


def _load_dotenv():
    """自动加载项目根目录下的 .env 文件（不覆盖已存在的系统环境变量）。"""
    base = os.environ.get("MUSE2API_HOME") or _DEFAULT_BASE_DIR
    env_path = os.path.join(base, ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip()
                v = _clean_env_value(v)
                if k and k not in os.environ:
                    os.environ[k] = v
    except OSError:
        pass


_load_dotenv()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int, minimum: int = 0) -> int:
    """整数环境变量，非法值回退默认值，并按 minimum 下限收敛。"""
    try:
        value = int(_env(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _env_flag(key: str, default: str = "0") -> bool:
    return _env(key, default).strip().lower() not in ("", "0", "false", "no", "off")


def _detect_chromium() -> str:
    """优先使用 MUSE2API_CHROMIUM；若未设置或路径不存在，则自动探测系统已安装的 Chromium/Chrome。"""
    configured = os.environ.get("MUSE2API_CHROMIUM", "").strip()
    if configured and (os.path.isfile(configured) or shutil.which(configured)):
        return configured
    candidates = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "chromium",
        "chromium-browser",
        "google-chrome",
        "chrome",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if os.path.isfile(c) or shutil.which(c):
            return c
    return configured or "chromium"


@dataclass
class Config:
    base_dir: str = field(default_factory=lambda: _env("MUSE2API_HOME", _DEFAULT_BASE_DIR))
    host: str = field(default_factory=lambda: _env("MUSE2API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("MUSE2API_PORT", "18610")))

    # 浏览器
    chromium: str = field(default_factory=_detect_chromium)
    cdp_port: int = field(default_factory=lambda: int(_env("MUSE2API_CDP_PORT", "19210")))
    home_dir: str = field(default_factory=lambda: _env("MUSE2API_HOME_DIR", os.path.expanduser("~")))
    extra_path: str = field(default_factory=lambda: _env("MUSE2API_EXTRA_PATH", "/snap/bin"))
    site_url: str = field(default_factory=lambda: _env("MUSE2API_SITE", "https://muse.ai/"))
    login_wait: int = field(default_factory=lambda: int(_env("MUSE2API_LOGIN_WAIT", "60")))

    # 浏览器 profile 根目录。
    # 踩过的坑：snap 版 chromium 受 AppArmor 约束，只能读写 $HOME 下的路径。
    # 传 --user-data-dir=/opt/... 或 /tmp/... 不会报错，但会被静默忽略，
    # 浏览器回落到 ~/snap/chromium/common/chromium。
    # 所以必须落在 $HOME 下（不要用点开头的隐藏目录，snap 的 home 接口排除隐藏文件）。
    profile_root: str = field(
        default_factory=lambda: _env("MUSE2API_PROFILE_ROOT",
                                     os.path.join(os.path.expanduser("~"),
                                                  "muse2api-profiles")))

    # 鉴权
    api_key: str = field(default_factory=lambda: _env("MUSE2API_KEY", ""))

    # 对外地址（管理页面显示「接入地址」用；留空则页面用当前域名兜底）
    public_base: str = field(
        default_factory=lambda: _env("MUSE2API_PUBLIC_BASE", ""))

    # 允许跨域调用导入接口的来源（Cookie 助手脚本从 muse.ai 页面提交时用）
    cors_origins: str = field(
        default_factory=lambda: _env("MUSE2API_CORS_ORIGINS",
                                     "https://muse.ai,https://www.muse.ai"))

    # 生成
    image_timeout: int = field(default_factory=lambda: int(_env("MUSE2API_IMAGE_TIMEOUT", "240")))
    video_timeout: int = field(default_factory=lambda: int(_env("MUSE2API_VIDEO_TIMEOUT", "600")))
    chat_timeout: int = field(default_factory=lambda: int(_env("MUSE2API_CHAT_TIMEOUT", "300")))
    max_concurrency: int = field(
        default_factory=lambda: _env_int("MUSE2API_CONCURRENCY", 2, 1))

    # 对话提示词上限（字符）。超长时截断中段，避免把整段历史塞进浏览器导致卡死。
    chat_max_chars: int = field(
        default_factory=lambda: _env_int("MUSE2API_CHAT_MAX_CHARS", 120000, 1000))

    # 单 IP 每分钟 /v1/* 请求上限；0 表示不限流。
    rate_limit: int = field(
        default_factory=lambda: _env_int("MUSE2API_RATE_LIMIT", 120, 0))

    # 后台保活轮询周期（秒）。管理页文案按 30 分钟展示。
    keepalive_interval: int = field(
        default_factory=lambda: _env_int("MUSE2API_KEEPALIVE_INTERVAL", 1800, 60))

    # 是否允许导入与已有账号完全相同的 cookie（默认去重，避免重复占号）。
    allow_duplicate_accounts: bool = field(
        default_factory=lambda: _env_flag("MUSE2API_ALLOW_DUPLICATE_ACCOUNTS", "0"))

    # 维护者模式：开启后 /admin/repo/push 才允许把本机代码推回 GitHub。
    maintainer: bool = field(
        default_factory=lambda: _env_flag("MUSE2API_MAINTAINER", "0"))

    # 媒体访问控制：默认保持 OpenAI 兼容的匿名可读；开启后需 Bearer 或签名 URL。
    media_require_auth: bool = field(
        default_factory=lambda: _env_flag("MUSE2API_MEDIA_REQUIRE_AUTH", "0"))
    # 签名媒体 URL 有效期（秒）；0 表示不过期（仍可用 token 访问）。
    media_url_ttl: int = field(
        default_factory=lambda: _env_int("MUSE2API_MEDIA_URL_TTL", 0, 0))
    media_token: str = field(
        default_factory=lambda: _env("MUSE2API_MEDIA_TOKEN", ""))

    # 媒体 / 任务保留策略：0 表示永不自动清理。
    media_retention_days: int = field(
        default_factory=lambda: _env_int("MUSE2API_MEDIA_RETENTION_DAYS", 0, 0))
    task_retention: int = field(
        default_factory=lambda: _env_int("MUSE2API_TASK_RETENTION", 500, 0))

    # Chromium 相关运维参数
    no_sandbox: bool = field(
        default_factory=lambda: _env_flag("MUSE2API_NO_SANDBOX", "1"))
    chromium_log_max_mb: int = field(
        default_factory=lambda: _env_int("MUSE2API_CHROMIUM_LOG_MAX_MB", 10, 1))
    debug_dump_keep: int = field(
        default_factory=lambda: _env_int("MUSE2API_DEBUG_DUMP_KEEP", 5, 1))

    # 参考图输入默认只允许调用方直接提供数据和公网 URL。
    # 仅可信单用户部署可显式设为 1 恢复服务器本地文件或私网抓取。
    ref_image_local_files: bool = field(
        default_factory=lambda: _env("MUSE2API_REF_IMAGE_LOCAL_FILES", "0").strip() == "1")
    ref_image_private_fetch: bool = field(
        default_factory=lambda: _env("MUSE2API_REF_IMAGE_PRIVATE_FETCH", "0").strip() == "1")

    # 工具调用（function calling）协议适配开关，**默认关闭**。
    # 实测 muse.ai 的助手会明确拒绝输出"伪工具调用"（原话：「我不会按这种 JSON
    # 格式输出'伪工具调用'」），强行注入协议反而会污染正常回答。
    # 所以默认只做「参数兼容」（客户端传 tools 不会 422），不注入、不解析。
    # 若目标模型行为有变，可设 MUSE2API_TOOL_PROTOCOL=1 打开这层适配再试。
    tool_protocol: bool = field(
        default_factory=lambda: _env("MUSE2API_TOOL_PROTOCOL", "0").strip() != "0")

    # 保活设置：是否对已禁用的账号执行自动保活，**默认关闭**。
    # 开启后，被管理员在后台手动禁用的账号仍会由后台守护进程执行自动保活与 VM 唤醒，
    # 保持会话活性不失效，但依然不会参与正常业务生图、生视频与对话轮转调度。
    keepalive_disabled_accounts: bool = field(
        default_factory=lambda: _env("MUSE2API_KEEPALIVE_DISABLED_ACCOUNTS", "0").strip() != "0")

    @property
    def data_dir(self) -> str:
        return os.path.join(self.base_dir, "data")

    @property
    def media_secret(self) -> str:
        """签名媒体 URL 用；未单独配置时退化为 API Key。"""
        return self.media_token or self.api_key or "muse2api-media"

    @property
    def media_dir(self) -> str:
        return os.path.join(self.data_dir, "media")

    @property
    def download_dir(self) -> str:
        return os.path.join(self.data_dir, "downloads")

    @property
    def profile_dir(self) -> str:
        """生成用浏览器 profile。"""
        return os.path.join(self.profile_root, "generate")

    @property
    def accounts_file(self) -> str:
        return os.path.join(self.data_dir, "accounts.json")

    @property
    def tasks_file(self) -> str:
        return os.path.join(self.data_dir, "tasks.json")

    def ensure_dirs(self):
        for d in (self.base_dir, self.data_dir, self.media_dir, self.download_dir,
                  self.profile_dir):
            os.makedirs(d, exist_ok=True)


CFG = Config()
