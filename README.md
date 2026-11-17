# 音视频批量下载工具

基于 yt-dlp + FFmpeg 的桌面端音视频批量下载工具。

## 使用方法

### 1. 图形界面版（推荐）

双击运行 `dist/音视频批量下载V1.0.exe`：

1. 选择 **下载类型**：视频或音频
2. 选择 **输出格式**：
   - 音频：mp3、m4a、wav、flac、opus
   - 视频：mp4、mkv、webm
3. 选择 **保存目录**（默认：`C:\Users\你的用户名\Downloads\音视频下载`）
4. 可选：点击 **Cookies 选择** 加载浏览器 cookies 文件（YouTube 等需要登录的站点）
5. 在下方文本框 **粘贴 URL**，或点击 **导入 TXT** 从文件读取地址
6. 点击 **开始下载**，实时显示进度和日志

**界面说明：**

- **粘贴地址**：自动从剪贴板粘贴 URL
- **导入 TXT**：从文本文件读取 URL 列表（每行一个）
- **清空**：清除输入框中的 URL
- **停止**：中断正在进行的下载任务
- 所有设置（cookies 路径、保存目录等）会自动记忆，下次打开自动恢复

### 2. 命令行版

打开命令行，进入 `dist` 目录，运行：

```bash
# 从 TXT 文件读取 URL 列表
批量下载音频V1.0.exe -f urls.txt

# 直接在命令行输入 URL
批量下载音频V1.0.exe -u "https://www.youtube.com/watch?v=xxx"

# 指定输出目录和格式
批量下载音频V1.0.exe -f urls.txt -o D:\我的音乐 -t m4a

# 指定 cookies 文件
批量下载音频V1.0.exe -f urls.txt -c cookies.txt
```

**命令行参数：**

| 参数 | 说明 |
|------|------|
| `-u URL [URL...]` | 直接输入多个 URL |
| `-f 文件.txt` | 从 TXT 文件读取 URL（每行一个） |
| `-o 目录` | 输出目录（默认当前目录） |
| `-c cookies.txt` | cookies 文件路径（YouTube 等需要） |
| `-t 格式` | 输出格式：mp3/m4a/wav/opus/flac |
| `-q 质量值` | 音频质量（0-320，默认 192） |
| `-r 重试次数` | 下载失败重试次数（默认 10） |

## FFmpeg 自动检测

程序会自动按以下顺序查找 FFmpeg：

1. 打包内嵌（已包含在 exe 中）
2. 同目录下的 `ffmpeg/` 文件夹
3. 递归搜索 `ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe`
4. 系统 PATH 中的 ffmpeg

找不到时会弹窗提示下载，点击下载后自动获取并解压。

## 依赖

- Python 3.10+（源码运行时需要）
- yt-dlp
- FFmpeg（已内置，自动检测）

## 从源码运行

```bash
pip install yt-dlp
python media_downloader.py
```

## 文件结构

```
├── media_downloader.py           # GUI 版源码
├── 批量下载音频.py               # 命令行版源码
├── dist/
│   ├── 音视频批量下载V1.0.exe    # GUI 版（94 MB）
│   └── 批量下载音频V1.0.exe      # 命令行版（23 MB）
├── ffmpeg-master-latest-win64-gpl/  # FFmpeg 完整包（备用）
│   └── bin/
│       ├── ffmpeg.exe
│       └── ffprobe.exe
├── cookies.txt                   # 示例 cookies 文件
├── x.com_cookies.txt             # x.com cookies 文件
└── history/                      # 旧版脚本（历史参考）
    ├── 视频下载/
    └── 音频下载/
```

## 注意事项

- YouTube 等部分站点需要 cookies 文件才能正常下载
- cookies 文件可从浏览器导出（推荐扩展：Get cookies.txt LOCALLY）
- 已下载视频会自动记录在 `archive.txt`，下次运行自动跳过
- 下载过程中如需取消，点击"停止"按钮即可
- 文件命名格式：`标题 [视频ID].格式`，避免文件名过长