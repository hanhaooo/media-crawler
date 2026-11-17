"""Desktop batch media downloader powered by yt-dlp."""
import json
import os
import queue
import re
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import yt_dlp


# ─── 配置 ───

FORMATS = {'视频': ('mp4', 'mkv', 'webm'), '音频': ('mp3', 'm4a', 'wav', 'flac', 'opus')}
BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
CONFIG = Path(os.getenv('LOCALAPPDATA', str(BASE))) / 'MediaBatchDownloader' / 'settings.json'

# FFmpeg 下载镜像（GitHub Release / CDN）
FFMPEG_DOWNLOAD_URL = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
FFMPEG_MINI_URL = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'


# ─── 工具函数 ───

def has_js_runtime():
    """检测是否有可用的 JS 运行时（deno/node）。"""
    import shutil
    return bool(shutil.which('deno') or shutil.which('node'))


def parse_urls(text):
    """解析纯文本中的 URL，去重。"""
    result = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        for url in re.split(r'\s+', line):
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                raise ValueError('无效 URL：' + url[:120])
            if url not in result:
                result.append(url)
    return result


def read_txt(path):
    """读取 TXT 文件（自动检测编码）。"""
    raw = Path(path).read_bytes()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16')
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('TXT 编码无法识别，请保存为 UTF-8。')


def ffmpeg_dir():
    """查找 FFmpeg 可执行文件目录。

    查找顺序：
    1. PyInstaller 打包内的 ffmpeg（_MEIPASS）
    2. 同目录下的 ffmpeg 文件夹
    3. 递归搜索同目录下的所有 ffmpeg.exe
    4. 系统 PATH 中的 ffmpeg
    """
    # 1. 打包环境
    bundled = Path(getattr(sys, '_MEIPASS', str(BASE))) / 'ffmpeg'
    if (bundled / 'ffmpeg.exe').exists():
        return str(bundled)

    # 2. 同目录 ffmpeg/ffmpeg.exe
    exe_dir = Path(getattr(sys, '_MEIPASS', str(BASE)))
    if (exe_dir / 'ffmpeg' / 'ffmpeg.exe').exists():
        return str(exe_dir / 'ffmpeg')

    # 3. 递归搜索 exe 同目录及子目录
    for root, dirs, files in os.walk(exe_dir):
        if 'ffmpeg.exe' in files:
            return str(Path(root).parent)

    # 4. 系统 PATH
    import shutil
    exe = shutil.which('ffmpeg')
    if exe:
        return str(Path(exe).parent)

    return None


def check_ffmpeg_available():
    """检查 FFmpeg 是否存在。不存在则弹窗引导下载。"""
    fdir = ffmpeg_dir()
    if fdir:
        return True, fdir

    # 弹窗提示
    msg = (
        '未检测到 FFmpeg！\n\n'
        'FFmpeg 是音视频转换必需的组件。\n\n'
        '请点击"下载"自动获取，或手动下载后放到本程序同目录。\n\n'
        '下载地址：\n'
        'https://github.com/BtbN/FFmpeg-Builds/releases/tag/auto\n'
        '请选择 win64-gpl 版本的 zip 下载并解压。\n\n'
        '解压后请确保目录结构为：\n'
        '  ffmpeg/\n'
        '    ffmpeg.exe\n'
        '    ffprobe.exe\n'
    )

    download_url = FFMPEG_DOWNLOAD_URL
    try:
        btn = messagebox.askyesno('缺少 FFmpeg', msg)
    except Exception:
        return False, None

    if btn:
        # 自动下载
        _download_ffmpeg(download_url)
        # 下载完成后重新检测
        return check_ffmpeg_available()

    return False, None


def _download_ffmpeg(url):
    """后台下载 FFmpeg 并解压到同目录。"""
    import urllib.request
    import zipfile
    import tempfile

    exe_dir = Path(getattr(sys, '_MEIPASS', str(BASE)))
    status_label = None  # 由调用方设置

    def set_progress(text):
        nonlocal status_label
        if status_label:
            status_label.config(text=text)

    try:
        set_progress('正在下载 FFmpeg（约 190 MB，请耐心等待）...')
        zip_path = exe_dir / 'ffmpeg-temp.zip'
        total_size = 0
        downloaded = 0

        def reporthook(block_num, block_size, total_size_local):
            nonlocal downloaded
            downloaded = block_num * block_size
            if total_size_local > 0:
                percent = min(100, downloaded / total_size_local * 100)
                mb = downloaded / (1024 * 1024)
                total_mb = total_size_local / (1024 * 1024)
                set_progress(f'正在下载... {percent:.1f}% ({mb:.1f}/{total_mb:.1f} MB)')

        # 获取文件大小
        try:
            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get('Content-Length', 0))
        except Exception:
            pass

        urllib.request.urlretrieve(url, str(zip_path), reporthook)
        set_progress('正在解压 FFmpeg...')
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(exe_dir)

        # 清理临时文件
        try:
            zip_path.unlink()
        except Exception:
            pass

        # 查找解压后的 ffmpeg 目录并重命名
        for root, dirs, files in os.walk(exe_dir):
            for d in dirs:
                if d.startswith('ffmpeg-master') and (exe_dir / d / 'bin' / 'ffmpeg.exe').exists():
                    target = exe_dir / 'ffmpeg'
                    if target.exists():
                        import shutil
                        shutil.rmtree(target)
                    target.rename(exe_dir / d)
                    messagebox.showinfo('下载完成', 'FFmpeg 已下载并解压到程序目录，可以开始使用了！')
                    return
            break  # 只找第一层

        messagebox.showwarning('解压完成', 'FFmpeg 已下载但目录结构异常，请手动将 ffmpeg.exe 放到程序同目录。')

    except urllib.error.URLError as e:
        messagebox.showerror('下载失败', f'无法下载 FFmpeg：\n{e}\n\n请手动从以下地址下载：\n{url}')
    except zipfile.BadZipFile:
        messagebox.showerror('下载失败', 'FFmpeg 下载不完整，请重新下载。')
    except Exception as e:
        messagebox.showerror('下载失败', f'FFmpeg 下载或解压失败：\n{e}')
    finally:
        if status_label:
            status_label.config(text='FFmpeg 下载完成')


def format_quality(fmt):
    """返回各音频格式的质量参数。"""
    return {
        'mp3': '192',
        'm4a': '128',
        'wav': None,
        'opus': '96',
        'flac': None,
    }.get(fmt)


def show_error(msg):
    """弹窗显示错误。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "音视频批量下载", 0x10)
    except Exception:
        pass
    try:
        log_path = Path(getattr(sys, '_MEIPASS', str(BASE))) / 'error_log.txt'
        log_path.write_text(msg, encoding='utf-8')
    except Exception:
        pass
    sys.exit(1)


# ─── 核心逻辑 ───

def download_audio(ydl_opts, url, logger=None):
    """下载单个音频/视频，返回 (success, message)。"""
    class Hook:
        def __init__(self, cb):
            self.cb = cb
        def __call__(self, d):
            if self.cb:
                self.cb(d)

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes', d.get('total_bytes_estimate', 0))
            if total:
                percent = d['downloaded_bytes'] / total * 100
                speed_raw = d.get('speed')
                speed = speed_raw / 1024 / 1024 if speed_raw else 0
                if logger:
                    logger(f"\r📥 下载进度: {percent:.1f}%  速度: {speed:.2f} MB/s", end='')
        elif d['status'] == 'finished':
            if logger:
                logger("\n✅ 文件下载完成，正在转码...")

    opts = dict(ydl_opts)
    opts.setdefault('progress_hooks', []).append(Hook(progress_hook))

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return True, '下载完成'
    except Exception as e:
        return False, str(e)


def options(mode, fmt, output, cookies='', hook=None, logger=None):
    """构建 yt-dlp 配置。"""
    opts = {
        'outtmpl': str(Path(output) / '%(title).150B [%(id)s].%(ext)s'),
        'windowsfilenames': True, 'continuedl': True, 'overwrites': False,
        'noplaylist': True, 'socket_timeout': 20, 'retries': 10, 'fragment_retries': 10,
        'quiet': True, 'noprogress': True, 'ffmpeg_location': ffmpeg_dir(),
        'progress_hooks': [hook] if hook else [],
        'postprocessor_hooks': [hook] if hook else [],
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios'],
                'skip': ['dash', 'hls'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        },
        'cookiesfrombrowser': None,
    }
    if logger:
        opts['logger'] = logger
    if cookies:
        opts['cookiefile'] = cookies
    if mode == '音频':
        opts.update(format='bestaudio/best', postprocessors=[{
            'key': 'FFmpegExtractAudio', 'preferredcodec': fmt, 'preferredquality': '192'}])
    else:
        opts.update(format='bestvideo+bestaudio/best', merge_output_format=fmt,
                    postprocessors=[{'key': 'FFmpegVideoConvertor', 'preferedformat': fmt}])
        if fmt == 'mp4':
            opts['postprocessor_args'] = {'VideoConvertor+ffmpeg_o': ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-c:a', 'aac']}
        elif fmt == 'webm':
            opts['postprocessor_args'] = {'VideoConvertor+ffmpeg_o': ['-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0', '-c:a', 'libopus']}
    return opts


class Logger:
    def __init__(self, emit):
        self.emit = emit
    def debug(self, msg):
        if not msg.startswith('[debug]'):
            self.emit('log', str(msg))
    def warning(self, msg):
        self.emit('log', '警告：' + str(msg))
    def error(self, msg):
        self.emit('log', '失败：' + str(msg))


# ─── GUI ───

class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.controls = []
        root.title('音视频批量下载 V1.0')
        root.geometry('1000x850')
        root.minsize(820, 780)
        root.configure(bg='#edf2f3')
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background='white', foreground='#26383d', font=('Microsoft YaHei UI', 10))
        style.configure('TEntry', padding=8, fieldbackground='white')
        style.configure('TCombobox', padding=6)
        style.configure('TButton', padding=(14, 8), background='#eaf0f1')
        style.configure('Accent.TButton', background='#147d70', foreground='white')
        style.map('Accent.TButton', background=[('active', '#10675d'), ('disabled', '#aabdb9')])
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 20, 'bold'))
        style.configure('Muted.TLabel', foreground='#6b7c82')
        style.configure('Horizontal.TProgressbar', background='#168477', troughcolor='#eaf0ee')
        try:
            cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            cfg = {}
        self.mode = tk.StringVar(value=cfg.get('mode', '视频'))
        if self.mode.get() not in FORMATS:
            self.mode.set('视频')
        self.fmt = tk.StringVar(value=cfg.get('format', FORMATS[self.mode.get()][0]))
        self.output = tk.StringVar(value=cfg.get('output', str(Path.home() / 'Downloads' / '音视频下载')))
        self.cookies = tk.StringVar(value=cfg.get('cookies', ''))
        self.status = tk.StringVar(value='准备就绪')
        self.progress_text = tk.StringVar(value='尚未开始')
        self.js_runtime_ok = tk.BooleanVar(value=has_js_runtime())
        self._ffmpeg_ok = None  # 缓存检测结果
        page = ttk.Frame(root, padding=24)
        page.pack(fill='both', expand=True, padx=12, pady=12)
        ttk.Label(page, text='音视频批量下载', style='Title.TLabel').pack(anchor='w', pady=(0, 16))
        top = ttk.Frame(page)
        top.pack(fill='x', pady=(0, 12))
        ttk.Label(top, text='下载类型').pack(side='left', padx=(0, 12))
        for label in FORMATS:
            radio = ttk.Radiobutton(top, text=label, variable=self.mode, value=label, command=self.change_mode)
            radio.pack(side='left', padx=(0, 18))
            self.controls.append(radio)
        ttk.Label(top, text='输出格式').pack(side='left', padx=(20, 12))
        self.formats = ttk.Combobox(top, textvariable=self.fmt, state='readonly', width=10)
        self.formats.pack(side='left')
        self.change_mode()
        paths = ttk.Frame(page)
        paths.pack(fill='x')
        paths.columnconfigure(1, weight=1)
        for row, (label, var, cmd) in enumerate([('保存目录', self.output, self.pick_output), ('Cookies（手动选择）', self.cookies, self.pick_cookies)]):
            ttk.Label(paths, text=label).grid(row=row, column=0, sticky='w', padx=(0, 14), pady=4)
            entry = ttk.Entry(paths, textvariable=var, width=20)
            entry.grid(row=row, column=1, sticky='ew', pady=4)
            button = ttk.Button(paths, text='选择…', command=cmd)
            button.grid(row=row, column=2, padx=(12, 0), pady=4)
            self.controls.extend([entry, button])
            if row == 1:
                self.lbl_cookies_state = ttk.Label(paths, text='', foreground='#888')
                self.lbl_cookies_state.grid(row=1, column=3, sticky='w', padx=(12, 0), pady=4)
        # JS 运行时提示
        if not self.js_runtime_ok.get():
            hint = ttk.Label(paths, text='⚠ 未检测到 deno/node，YouTube 部分格式可能无法获取（加 cookies 可绕过）', foreground='#946820')
            hint.grid(row=2, column=0, columnspan=3, sticky='w', pady=(4, 0))
        # FFmpeg 状态
        self._check_ffmpeg_on_init()
        bar = ttk.Frame(page)
        bar.pack(fill='x', pady=(16, 8))
        ttk.Label(bar, text='下载地址', font=('Microsoft YaHei UI', 11, 'bold')).pack(side='left')
        for label, cmd in [('导入 TXT', self.import_txt), ('粘贴地址', self.paste), ('清空', self.clear)]:
            b = ttk.Button(bar, text=label, command=cmd)
            b.pack(side='right', padx=(8, 0))
            self.controls.append(b)
        self.urls = scrolledtext.ScrolledText(page, height=6, wrap='word', relief='flat', bg='#f6f8f9', padx=12, pady=10, font=('Microsoft YaHei UI', 10))
        self.urls.pack(fill='x')
        action = ttk.Frame(page)
        action.pack(fill='x', pady=12)
        ttk.Label(action, textvariable=self.status, style='Muted.TLabel').pack(side='left')
        self.start_button = ttk.Button(action, text='开始下载', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='right')
        self.stop_button = ttk.Button(action, text='停止', state='disabled', command=self.stop)
        self.stop_button.pack(side='right', padx=10)
        self.progress = ttk.Progressbar(page, maximum=100)
        self.progress.pack(fill='x')
        ttk.Label(page, textvariable=self.progress_text, style='Muted.TLabel').pack(anchor='w', pady=(6, 12))
        ttk.Label(page, text='任务日志', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(0, 8))
        self.logs = scrolledtext.ScrolledText(page, height=6, wrap='word', state='disabled', relief='flat', bg='#f6f8f9', padx=12, pady=10, font=('Microsoft YaHei UI', 10))
        self.logs.pack(fill='both', expand=True)
        self.logs.tag_configure('error', foreground='#b43e47')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_cookies_state()
        root.after(100, self.poll)

    def _check_ffmpeg_on_init(self):
        """启动时检查 FFmpeg，缺失则弹窗引导。"""
        fdir = ffmpeg_dir()
        if fdir:
            self._ffmpeg_ok = True
        else:
            self._ffmpeg_ok = False
            msg = (
                '未检测到 FFmpeg！\n\n'
                'FFmpeg 是音视频转换必需的组件。\n\n'
                '请点击"下载"自动获取，或手动下载后放到本程序同目录。\n\n'
                '下载地址：\n'
                'https://github.com/BtbN/FFmpeg-Builds/releases\n'
                '请选择 win64-gpl 版本的 zip 下载并解压。\n\n'
                '解压后确保目录结构：\n'
                '  ffmpeg/\n'
                '    ffmpeg.exe\n'
                '    ffprobe.exe\n'
            )
            btn = messagebox.askyesno('缺少 FFmpeg', msg)
            if btn:
                threading.Thread(target=self._download_ffmpeg_thread, daemon=True).start()
            else:
                messagebox.showinfo('提示', '未下载 FFmpeg 将无法转换音视频格式，请先下载后再使用。')

    def _download_ffmpeg_thread(self):
        """后台下载 FFmpeg。"""
        def set_status(text):
            self.root.after(0, self._set_status_text, text)

        def _set_status_text(text):
            self.progress_text.set(text)

        def _after_done(ok):
            self.root.after(0, lambda: messagebox.showinfo('完成', 'FFmpeg 下载完成！') if ok else messagebox.showwarning('部分完成', 'FFmpeg 已下载但可能不完整，请检查程序目录。'))
            self.root.after(0, lambda: self._check_ffmpeg_on_init())

        try:
            _download_ffmpeg_threaded(FFMPEG_DOWNLOAD_URL, set_status)
            self.root.after(0, lambda: _after_done(True))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror('下载失败', str(e)))

    def _set_status_text(self, text):
        self.progress_text.set(text)

    def emit(self, kind, value):
        self.events.put((kind, value))

    def change_mode(self):
        self.formats.configure(values=FORMATS[self.mode.get()])
        if self.fmt.get() not in FORMATS[self.mode.get()]:
            self.fmt.set(FORMATS[self.mode.get()][0])

    def pick_output(self):
        p = filedialog.askdirectory()
        if p:
            self.output.set(p)

    def pick_cookies(self):
        p = filedialog.askopenfilename(filetypes=[('Cookies 文件', '*.txt'), ('所有文件', '*.*')])
        if p:
            self.cookies.set(p)
            self.refresh_cookies_state()

    def refresh_cookies_state(self):
        c = self.cookies.get().strip()
        if c and Path(c).is_file():
            size = Path(c).stat().st_size
            self.lbl_cookies_state.config(text=f'✓ {size:,} 字节', foreground='#0a7')
        else:
            self.lbl_cookies_state.config(text='✗ 未设置', foreground='#c33')

    def paste(self):
        try:
            self.urls.insert('end', '\n' + self.root.clipboard_get() + '\n')
        except tk.TclError:
            messagebox.showwarning('剪贴板', '剪贴板中没有文本。')

    def clear(self):
        self.urls.delete('1.0', 'end')

    def import_txt(self):
        path = filedialog.askopenfilename(filetypes=[('TXT 地址文件', '*.txt')])
        if path:
            try:
                text = read_txt(path)
                self.urls.insert('end', '\n' + text + '\n')
            except Exception as exc:
                messagebox.showerror('导入失败', str(exc))

    def set_busy(self, busy):
        self.busy = busy
        for control in self.controls:
            control.configure(state='disabled' if busy else 'normal')
        self.formats.configure(state='disabled' if busy else 'readonly')
        self.urls.configure(state='disabled' if busy else 'normal')
        self.start_button.configure(state='disabled' if busy else 'normal')
        self.stop_button.configure(state='normal' if busy else 'disabled')

    def start(self):
        if self.busy:
            return
        # 检查 FFmpeg
        if not self._ffmpeg_ok:
            ok, _ = check_ffmpeg_available()
            self._ffmpeg_ok = ok
            if not ok:
                messagebox.showerror('无法开始', '未找到 FFmpeg，请先下载或手动放置。')
                return
        try:
            urls = parse_urls(self.urls.get('1.0', 'end'))
            if not urls:
                raise ValueError('请粘贴 URL 或导入 TXT 地址文件。')
            if not self.output.get().strip():
                raise ValueError('请选择保存目录。')
            out = Path(self.output.get().strip()).expanduser().resolve()
            out.mkdir(parents=True, exist_ok=True)
            cookie = self.cookies.get().strip()
            if cookie and not Path(cookie).is_file():
                raise ValueError('Cookies 文件不存在。')
            if not ffmpeg_dir():
                raise ValueError('缺少 FFmpeg，请重新获取完整程序。')
            if not self.js_runtime_ok.get():
                self.emit('log', '⚠ 未检测到 deno/node，YouTube 部分格式可能不完整（加 cookies 可绕过）')
            cfg = dict(mode=self.mode.get(), format=self.fmt.get(), output=str(out), cookies=cookie)
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            messagebox.showerror('无法开始', str(exc))
            return
        self.cancel.clear()
        self.set_busy(True)
        self.progress['value'] = 0
        self.status.set(f'共 {len(urls)} 个地址，正在处理')
        self.emit('log', f'开始任务：{cfg["mode"]} / {cfg["format"].upper()}，保存到 {out}')
        threading.Thread(target=self.run, args=(urls, cfg), daemon=True).start()

    def stop(self):
        self.cancel.set()
        self.stop_button.configure(state='disabled')
        self.status.set('正在停止；若已进入转码，将等待当前转码结束')

    def hook(self, info):
        if self.cancel.is_set():
            raise yt_dlp.utils.DownloadError('用户停止下载')
        status = info.get('status')
        if status == 'downloading':
            total = info.get('total_bytes') or info.get('total_bytes_estimate') or 0
            percent = min(100, info.get('downloaded_bytes', 0) / total * 100) if total else 0
            speed = (info.get('speed') or 0) / 1048576
            self.emit('progress', (percent, f'当前流 {percent:.1f}%  |  {speed:.2f} MB/s'))
        elif status in ('finished', 'started', 'processing'):
            self.emit('progress', (100, '正在合并 / 转换格式…'))

    def run(self, urls, cfg):
        success = failed = 0
        try:
            for index, url in enumerate(urls, 1):
                if self.cancel.is_set():
                    break
                self.emit('status', f'正在处理 {index} / {len(urls)}')
                self.emit('progress', (0, '正在解析地址…'))
                self.emit('log', f'[{index}/{len(urls)}] {url}')
                try:
                    opts = options(cfg['mode'], cfg['format'], cfg['output'], cfg['cookies'], self.hook, Logger(self.emit))
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        result = ydl.download([url])
                    if self.cancel.is_set():
                        break
                    if result:
                        raise RuntimeError('下载引擎返回失败状态')
                    success += 1
                    self.emit('log', '完成：' + url)
                except Exception as exc:
                    if self.cancel.is_set():
                        break
                    failed += 1
                    self.emit('log', '失败：' + str(exc))
        finally:
            remaining = len(urls) - success - failed
            summary = f'{"已停止" if self.cancel.is_set() else "任务结束"}：完成 {success}，失败 {failed}，未完成 {remaining}'
            self.emit('log', summary)
            self.emit('done', summary)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log':
                    self.logs.configure(state='normal')
                    self.logs.insert('end', str(value) + '\n', 'error' if str(value).startswith('失败') else '')
                    self.logs.see('end')
                    self.logs.configure(state='disabled')
                elif kind == 'status':
                    self.status.set(value)
                elif kind == 'progress':
                    self.progress['value'], text = value
                    self.progress_text.set(text)
                elif kind == 'done':
                    self.set_busy(False)
                    self.status.set(value)
                    self.progress_text.set('已停止' if self.cancel.is_set() else '处理完成')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('任务进行中', '请先点击停止，等待当前任务结束后再关闭。')
            return
        self.root.destroy()


def _download_ffmpeg_threaded(url, status_callback):
    """后台线程下载的 FFmpeg（供线程调用）。"""
    import urllib.request
    import zipfile

    exe_dir = Path(getattr(sys, '_MEIPASS', str(BASE)))
    zip_path = exe_dir / 'ffmpeg-temp.zip'

    def reporthook(block_num, block_size, total_size_local):
        mb = (block_num * block_size) / (1024 * 1024)
        total_mb = total_size_local / (1024 * 1024) if total_size_local else 0
        status_callback(f'正在下载... {mb:.1f}/{total_mb:.1f} MB')

    total_size = 0
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=30) as response:
            total_size = int(response.headers.get('Content-Length', 0))
    except Exception:
        pass

    status_callback('正在下载 FFmpeg（约 190 MB）...')
    urllib.request.urlretrieve(url, str(zip_path), reporthook)
    status_callback('正在解压 FFmpeg...')

    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(exe_dir)

    try:
        zip_path.unlink()
    except Exception:
        pass

    # 查找解压后的 ffmpeg 目录并重命名
    for root, dirs, files in os.walk(exe_dir):
        for d in dirs:
            if d.startswith('ffmpeg-master') and (exe_dir / d / 'bin' / 'ffmpeg.exe').exists():
                target = exe_dir / 'ffmpeg'
                if target.exists():
                    import shutil
                    shutil.rmtree(target)
                target.rename(exe_dir / d)
                return
        break


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()