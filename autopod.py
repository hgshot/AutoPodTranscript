#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
播客逐字稿转换器 (AutoPodTranscript)
核心功能：RSS 解析、并发下载、Google Drive 断点续传、本地转录模块预留
"""

import os
import re
import xml.etree.ElementTree as ET
import requests
import time
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

# ==========================================
#             === 用户配置区 ===
# ==========================================

# 1. 基础设置
RSS_FEED_URL = ""  # 粘贴你想要同步的播客 RSS 源在“”内
LOCAL_SAVE_DIR = "./Podcast_Downloads"                 # 本地音频保存路径 (支持相对或绝对路径)

# 2. 流水线开关 (True 开启 / False 关闭)
ENABLE_GDRIVE_SYNC = True         # 下载完成后，是否自动同步至 Google Drive
ENABLE_LOCAL_TRANSCRIPT = False   # 下载完成后，是否触发本地 AI 转录 (预留接口)

# 3. Google Drive 配置 (仅在 ENABLE_GDRIVE_SYNC = True 时生效)
DRIVE_FOLDER_ID = ""              # 请填入你的 Google Drive 目标文件夹 ID (如：1LvImRm...)

# 4. 下载策略
CHECK_LIMIT = 10                  # 每次运行检查的最新集数 (填 0 表示全量扫描所有历史剧集)
MAX_WORKERS = 4                   # 并发下载/上传的线程数 (建议 3-5)
PROXY_URL = ""                    # 代理地址，针对国内环境 (例如："http://127.0.0.1:7890"，直连请留空)

# ==========================================


# --- 系统初始化与环境配置 ---
socket.setdefaulttimeout(None)  # 取消全局超时限制，防止大文件长连接断开

if PROXY_URL:
    os.environ['http_proxy'] = PROXY_URL
    os.environ['https_proxy'] = PROXY_URL
    os.environ['all_proxy'] = PROXY_URL
    print(f"🔗 已启用代理配置: {PROXY_URL}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

print_lock = threading.Lock()
def safe_print(msg, end="\n"):
    with print_lock:
        print(msg, end=end, flush=True)

# --- Google Drive 模块 (按需加载) ---
if ENABLE_GDRIVE_SYNC:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request as AuthRequest
    SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_gdrive_credentials():
    """获取 Google Drive API 授权凭证"""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    client_secrets_path = os.path.join(BASE_DIR, 'client_secrets.json')
    token_path = os.path.join(BASE_DIR, 'token.json')
    creds = None
    
    if not os.path.exists(client_secrets_path):
        raise FileNotFoundError("未找到 client_secrets.json！请先前往 Google Cloud Console 下载凭证并放入项目根目录。")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(AuthRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return creds

def check_file_in_gdrive(creds, filename, folder_id):
    """检查文件是否已在 Google Drive 中"""
    if not folder_id:
        raise ValueError("DRIVE_FOLDER_ID 为空，请在配置区填写目标文件夹 ID。")
    url = "https://www.googleapis.com/drive/v3/files"
    headers = {"Authorization": f"Bearer {creds.token}"}
    params = {
        "q": f"name = '{filename}' and '{folder_id}' in parents and trashed = false",
        "fields": "files(id)",
        "pageSize": 1
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        return len(resp.json().get("files", [])) > 0
    except:
        return False

def upload_to_gdrive_resumable(creds, local_filepath, filename, folder_id):
    """使用断点续传方式上传至 Google Drive"""
    file_size = os.path.getsize(local_filepath)
    upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "audio/mpeg",
        "X-Upload-Content-Length": str(file_size)
    }
    metadata = {"name": filename, "parents": [folder_id]}
    
    try:
        init_resp = requests.post(upload_url, headers=headers, json=metadata, timeout=60)
        init_resp.raise_for_status()
        session_uri = init_resp.headers.get("Location")
        
        with open(local_filepath, "rb") as f:
            upload_headers = {"Content-Length": str(file_size)}
            upload_resp = requests.put(session_uri, data=f, headers=upload_headers, timeout=None)
            upload_resp.raise_for_status()
        return True
    except Exception as e:
        raise Exception(f"云端同步中断: {e}")

# --- 本地处理模块 ---
def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return re.sub(r"[\s_]+", "_", name).strip("_. ")

def download_audio(url, local_filepath):
    """下载音频文件到本地"""
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=120) as r:
            r.raise_for_status()
            with open(local_filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        # 下载失败时清理不完整的本地文件
        if os.path.exists(local_filepath):
            os.remove(local_filepath)
        raise Exception(f"下载失败: {e}")

def local_transcript_trigger(local_filepath):
    """本地转录预留接口 (配合 faster-whisper 等)"""
    # 示例接口：你可以在这里调用你的本地转录 Python 脚本
    safe_print(f"  [模块] 🤖 触发本地转录流水线: {os.path.basename(local_filepath)}")
    # TODO: import whisper_model; whisper_model.transcribe(local_filepath)
    time.sleep(1) # 模拟处理时间
    safe_print(f"  [模块] 📝 本地转录完成 (Mock)")

# --- 核心流水线 ---
def process_pipeline(args_pack):
    """单集音频的处理流水线"""
    i, ep, total, creds, folder_id = args_pack
    ep_num = total - i
    filename = f"{ep_num:03d}_{sanitize_filename(ep['title'])}.mp3"
    local_filepath = os.path.join(LOCAL_SAVE_DIR, filename)

    try:
        # ==========================================
        # 步骤 1：本地下载处理
        # ==========================================
        if os.path.exists(local_filepath) and os.path.getsize(local_filepath) > 0:
            safe_print(f"[{ep_num}集] 💾 本地已存在: {filename}，跳过下载。")
        else:
            safe_print(f"[{ep_num}集] ⬇️ 开始下载至本地...")
            download_audio(ep['url'], local_filepath)
            safe_print(f"[{ep_num}集] ✅ 本地下载完成。")

        # ==========================================
        # 步骤 2：云端同步 (可选)
        # ==========================================
        if ENABLE_GDRIVE_SYNC:
            if check_file_in_gdrive(creds, filename, folder_id):
                safe_print(f"[{ep_num}集] ☁️ 云端已存在: {filename}，跳过同步。")
            else:
                safe_print(f"[{ep_num}集] ⬆️ 正在同步至 Google Drive...")
                upload_to_gdrive_resumable(creds, local_filepath, filename, folder_id)
                safe_print(f"[{ep_num}集] ☁️ 云端同步成功！")

        # ==========================================
        # 步骤 3：本地 AI 转录 (可选)
        # ==========================================
        if ENABLE_LOCAL_TRANSCRIPT:
            local_transcript_trigger(local_filepath)

        safe_print(f"[{ep_num}集] 🎉 全流水线处理完毕！\n")

    except Exception as e:
        safe_print(f"[{ep_num}集] ❌ 处理异常: {e}\n")

# --- 主程序入口 ---
def main():
    print("\n🚀 启动 AutoPodTranscript 播客处理流水线")
    print("--------------------------------------------------")
    
    # 检查并创建本地目录
    if not os.path.exists(LOCAL_SAVE_DIR):
        os.makedirs(LOCAL_SAVE_DIR)
        print(f"📁 已创建本地保存目录: {LOCAL_SAVE_DIR}")

    # 获取 Google 凭证 (仅当开启同步时)
    creds = None
    if ENABLE_GDRIVE_SYNC:
        print("🔐 正在验证 Google Drive 授权...")
        try:
            creds = get_gdrive_credentials()
        except Exception as e:
            print(f"❌ 凭证错误: {e}")
            return

    # 解析 RSS
    print(f"📡 正在获取播客列表: {RSS_FEED_URL}")
    try:
        resp = requests.get(RSS_FEED_URL, headers=HEADERS, timeout=60)
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"❌ 无法连接或解析 RSS 源: {e}")
        return

    episodes = []
    channel = root.find("channel")
    if channel is None: channel = root
    for item in channel.findall("item"):
        enc = item.find("enclosure")
        if enc is not None:
            episodes.append({
                "title": item.findtext("title", "Untitled"), 
                "url": enc.get("url")
            })
    
    # 智能翻转 (确保最新的一集排在最前面)
    if len(episodes) > 0 and ("001" in episodes[0]['title'] or "介绍" in episodes[0]['title']):
         episodes.reverse()

    total = len(episodes)
    check_count = total if CHECK_LIMIT <= 0 else min(CHECK_LIMIT, total)
    
    print(f"✅ 解析成功！共发现 {total} 集。")
    print(f"🎯 运行策略: 检查最新的 {check_count} 集")
    print(f"⚙️  模块状态: GDrive同步[{'开启' if ENABLE_GDRIVE_SYNC else '关闭'}] | 本地转录[{'开启' if ENABLE_LOCAL_TRANSCRIPT else '关闭'}]")
    print("--------------------------------------------------\n")

    # 构建任务队列
    tasks = []
    for i in range(check_count):
        ep = episodes[i]
        tasks.append((i, ep, total, creds, DRIVE_FOLDER_ID))

    # 并发执行
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        executor.map(process_pipeline, tasks)

    print("\n✅ 所有任务执行完毕！")

if __name__ == "__main__":
    main()