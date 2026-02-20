# 🎙️ 播客逐字稿转换器 (AutoPodTranscript)

AutoPodTranscript 是一套自动化播客处理流水线工具。支持通过 RSS 源批量提取并高速下载播客音频至本地硬盘，构建个人数字资产库。通过高度模块化设计，下载完成后可选择自动同步至 Google Drive 进行云端备份，或接入本地 AI 模型生成逐字稿，作为构建“听觉笔记系统”的前置引擎。

## ✨ 核心特性
💾 本地优先归档：音频文件持久化保存至本地硬盘，目录结构清晰，支持各类本地播放器或 NAS 归档。

🧩 模块化：下载、云端同步、AI 转录解耦，可实现仅下载、下载+同步+转录、下载+本地转录。

⚡️ 极速并发：支持多线程并发下载，充分利用网络带宽。

🔄 智能增量更新：内置本地与云端双重查重机制，每次运行自动跳过已存在文件，节省时间与流量。

🔗 代理兼容：针对国内网络环境优化，支持配置代理（如 Clash）连通海外源和 Google 服务。

## 🛠️ 准备工作
### 1. 基础环境
需安装 Python 3.7 或更高版本。

### 2. [可选] 配置 Google Drive 云端同步
若需开启自动云端备份（便于后续使用 Colab 免费转录），需配置 Google API：

访问 Google Cloud Console，创建项目并启用 Google Drive API。

配置 OAuth 同意屏幕，创建应用类型为桌面应用的 OAuth 客户端 ID。

下载生成的 JSON 文件，重命名为 client_secrets.json，放置于本项目根目录。

获取目标 Google Drive 文件夹的 ID（提取自浏览器 URL 末尾的字符串）。
(注：若不开启云端同步功能，可跳过此步)

## 📦 安装与配置
### 1. 克隆项目与安装依赖
将项目下载到本地后，在终端中运行以下命令安装依赖库：

Bash
git clone https://github.com/hgshot/AutoPodTranscript.git

cd AutoPodTranscript

pip install -r requirements.txt

### 2. 核心配置
编辑核心代码文件（如 autopod.py），在顶部的 === 用户配置区 === 根据需求调整参数：

Python

=== 用户配置区 ===

1. 基础设置
2. 
RSS_FEED_URL = "" # 播客 RSS 源地址

LOCAL_SAVE_DIR = "./Podcast_Downloads" # 本地音频保存路径

3. 流水线开关 (True开启 / False关闭)

ENABLE_GDRIVE_SYNC = True       # 下载完成后，是否同步到 Google Drive

ENABLE_LOCAL_TRANSCRIPT = False # 下载完成后，是否触发本地 AI 转录 (预留接口)

5. Google Drive 配置 (开启同步时需填写)

DRIVE_FOLDER_ID = "请在这里填入你的_Folder_ID"

6. 下载策略

CHECK_LIMIT = 10     # 每次扫描最新 N 集 (填 0 表示全量扫描)

MAX_WORKERS = 4      # 并发下载线程数

PROXY_URL = "http://127.0.0.1:7890" # 代理地址 (直连请留空 "")

## 🚀 运行说明
在终端中执行以下命令启动工具：

Bash
python autopod.py

## 运行逻辑：
脚本读取 RSS 源，比对 LOCAL_SAVE_DIR 目录，仅下载本地缺失的最新集数。

若开启 ENABLE_GDRIVE_SYNC，脚本采用断点续传方式同步文件至 Google Drive（首次运行需通过浏览器完成 Google 账号授权，后续依赖本地 token.json 静默运行）。

若开启 ENABLE_LOCAL_TRANSCRIPT，脚本将触发预设的本地转录模型接口。

## 💡 逐字稿转录方案
完成音频获取后，提供以下几种转录思路：

### 方案 A：☁️ 云端零成本转录 (Google Colab + Whisper) [推荐]
若已开启 ENABLE_GDRIVE_SYNC，音频文件已同步至 Google Drive。可利用 Google 提供的免费 GPU 算力进行极速转录，完全不消耗本地电脑性能：

新建笔记本：使用 Google 账号访问 Google Colab 并新建 Notebook。

切换至 GPU：点击菜单栏的 代码执行程序 -> 更改运行时类型，硬件加速器选择 T4 GPU。

挂载云盘：在代码块中运行以下代码，将 Google Drive 挂载至当前环境：

Python
from google.colab import drive
drive.mount('/content/drive')
安装开源转录模型 Whisper：

Bash
!pip install -U openai-whisper
一键转录：读取云盘中的音频文件并输出逐字稿：

Bash
替换为网盘内具体的音频路径
!whisper "/content/drive/MyDrive/你的播客文件夹/xxx.mp3" --model large --language zh
获取输出：生成的 .txt 文本及 .srt 字幕文件会自动保存在 Colab 当前目录中。可直接下载，或使用 Python 代码将其移动回 Google Drive 保存。

### 方案 B：💻 自动化本地插件转录
开启 ENABLE_LOCAL_TRANSCRIPT = True 后，可在代码预留接口中对接本地部署的 faster-whisper，实现“下载 -> 转录 -> 文本输出”的自动化闭环。适用于具备较高性能显卡或 Apple Silicon (M系列) 芯片的设备。

### 方案 C：📁 第三方工具处理
作为纯粹的“播客批量下载器”使用。将下载至本地 LOCAL_SAVE_DIR 的音频文件，批量导入 MacWhisper、飞书妙记、通义听悟等商业工具或平台进行处理。

## 🔒 安全声明
使用云端同步功能时，严禁将 client_secrets.json 和 token.json 上传至公开的代码仓库。
本项目已在 .gitignore 文件中默认排除上述文件。在执行 Git 提交时，请务必检查确认，以免造成个人数据泄露。
