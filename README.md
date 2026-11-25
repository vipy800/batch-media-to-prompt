# 全能媒体反推 · Batch Image & Video to Prompt

> 把图片和视频，批量反推成能直接用的 AI 提示词。  
> Batch-convert images and videos into reusable prompts with any vision LLM.

<!-- 发布前建议在此插入主界面截图：![主界面](docs/screenshot-main.png) -->

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows&logoColor=white)

**全能媒体反推**是一款本地运行的批量提示词反推工具。批量导入图片或视频，选择场景预设，调用你配置的视觉大模型，把画面拆解成构图、主体、光影、材质、镜头、风格和负面词等结构化描述，并导出为 TXT、CSV、JSON 或清单 ZIP。

它的重点不是“和模型聊一句”，而是把反推提示词变成一条能真正跑完几百个文件的批量工作流：任务队列、并发控制、失败重试、暂停/取消、断点续跑、本地历史和批量导出。

> English: A Windows batch tool that converts images and videos into reusable AI prompts through any vision LLM. Built for AI art, video creation, e-commerce visuals and asset tagging.

---

## 下载免安装版

> 建议保存到自己网盘，以后有更新会自动提醒。

| 网盘 | 下载地址 |
| --- | --- |
| 夸克云盘 | [https://pan.quark.cn/s/b1a851425017](https://pan.quark.cn/s/b1a851425017) |
| 迅雷云盘 | [https://pan.xunlei.com/s/VP7G5hz9X-XQowHUqRqamcFdA1?pwd=27rv](https://pan.xunlei.com/s/VP7G5hz9X-XQowHUqRqamcFdA1?pwd=27rv) |

迅雷提取码：`27rv`

解压后双击 `全能媒体反推.exe` 即可使用，无需安装 Python，支持 Windows 10/11 64 位。

---

## 目录

- [下载免安装版](#下载免安装版)
- [为什么做这个工具](#为什么做这个工具)
- [核心功能](#核心功能)
- [快速开始](#快速开始)
- [支持的模型接口](#支持的模型接口)
- [适用场景](#适用场景)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [本地数据与隐私](#本地数据与隐私)
- [常见问题](#常见问题)
- [从源码构建](#从源码构建)
- [English Overview](#english-overview)

---

## 为什么做这个工具

给一张图写 Prompt 不难；给 300 张图写 Prompt，是另一回事。

大多数工具停留在“上传一张、聊一句、复制一段”的阶段。全能媒体反推把这件事变成可管理的工作流：

- 一次拖入整个文件夹，自动排队处理；
- 图片走图片预设，视频自动抽帧拼图后分析；
- 失败自动重试，大面积鉴权失败自动暂停，避免白跑；
- 结果实时落盘，随时中断、续跑、单项重跑；
- 导出 TXT / CSV / JSON / ZIP，直接进入下一环生产。

---

## 核心功能

### 批量与调度

- **批量处理**：多选拖拽或扫描整个文件夹，一次处理几百个文件
- **并发 1–8**：线程池调度，实时进度、ETA、暂停 / 继续 / 取消
- **自动分流**：图片走图片预设；视频自动抽帧拼图后交给视觉模型
- **失败重试**：5xx / 超时退避重试；401 / 403 自动暂停整任务
- **断点续跑**：重启后可重试历史任务，已完成结果不重跑
- **超时可控**：默认 600 秒，可自定义 10–7200 秒，带常用时长快捷按钮

### 预设与提示词

- **30 套内置预设，9 大场景分组**：通用、人像/服饰、电商/产品、空间/建筑、插画/游戏、影像/风格、平面/文字、质检/修复、视频
- **自定义提示词**：本次要求可临时填写，不改预设；也可“存为我的预设”
- **图片与视频分别配置**：可分别选择预设、分别填写要求
- **中英双语输出**：支持中文标准反推、英文 SD/MJ/FLUX 提示词、风格解析等

### 模型接入

- **多服务商**：硅基流动、智谱 AI、魔塔社区、七牛云一键填好地址与模型
- **通用接口**：任意 OpenAI 兼容地址
- **本地模型**：Ollama / LM Studio / llama.cpp / vLLM，任意端口，一键扫描本机服务
- **模型自动发现**：自动拉取模型列表，标注“视觉 / 文本”，并选择可用视觉模型
- **开跑前体检**：地址、Key、模型任一不可用即拦截并说明原因
- **本机免 Key**：本机或内网模型地址无需 API Key

### 结果与数据

- **省 token**：图片自动压缩到 1600px；视频抽 9 帧拼成一张触点图
- **多格式导出**：TXT / CSV / 清单 ZIP，任务结束自动落盘 `results.csv` + `results.json`
- **本地任务库**：SQLite 记录，随时回看、复制、单项重跑
- **一键自检**：9 项检查逐条给出结论与修法，包含真实看图测试
- **客户速查卡**：`客户速查卡-A4.pdf` 一页打印版，含三步、接口表、参数和报错对照

---

## 快速开始

### 方式一：免安装版（推荐给普通用户）

1. 从上方网盘地址，或仓库右侧 **Releases** 下载 `全能媒体反推-v4.0-免安装版.zip`
2. 解压后双击 `全能媒体反推.exe`
3. 浏览器自动打开；进入“设置”，填写接口地址、API Key 和视觉模型
4. 点“测试连接”，通过后保存
5. 回到主界面，拖入图片或视频，选择预设，开始任务

目标电脑无需安装 Python，Windows 10/11 64 位即可。

### 方式二：源码运行（适合二次开发）

在 GitHub 页面点 **Code → Download ZIP**，或下载 Releases 中的源码包，解压后进入项目目录。

Windows 下双击 `start_simple.bat`，脚本会自动探测 Python、创建 `.venv`、安装依赖并启动。

也可以手动启动：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

打包 Windows 免安装版：双击 `build.bat`，或运行：

```bash
python build.py
```

产物位于 `dist\全能媒体反推\`。

> 第一次运行如端口被占用，程序会自动顺延端口，不需要手动改配置。

---

## 支持的模型接口

| 接口类型 | 说明 |
| --- | --- |
| 硅基流动 | 一键填充地址与推荐视觉模型 |
| 智谱 AI | 一键填充地址与 GLM 视觉模型 |
| 魔塔社区 | 一键填充地址与推荐模型 |
| 七牛云 | 一键填充地址与推荐模型 |
| 通用接口 | 任意 OpenAI 兼容 `/v1` 地址 |
| 本地 AI | Ollama / LM Studio / llama.cpp / vLLM，本机地址免 Key |

设置页可自动扫描本机常见端口，也可手动填写。模型列表拉取失败时会回退到推荐列表，不影响手动配置。

---

## 适用场景

- **AI 绘画 / 视频创作者**：复刻参考图，沉淀个人提示词库
- **电商与品牌视觉**：批量拆解竞品图、白底图、模特图、场景图
- **设计与摄影团队**：把视觉参考转成构图、布光、材质和镜头描述
- **素材库与数据团队**：批量生成结构化标签与画面描述
- **模型与工具评测**：统一预设下对比不同视觉模型的反推质量
- **短视频与直播团队**：分镜分析、运镜复刻、带货脚本拆解

---

## 技术栈

- Python 3.10+ / FastAPI / Uvicorn
- Jinja2 + 原生 JavaScript 单页界面
- OpenCV + Pillow：图片压缩、视频抽帧、缩略图、拼图
- SQLite WAL：本地任务、结果与历史
- PyInstaller：Windows onedir 免安装包

---

## 项目结构

```text
run.py              启动入口（端口顺延 + 自动打开浏览器）
webapp/config.py    路径、配置、内置预设
webapp/client.py    模型接口客户端（重试 / 限流 / 错误分类）
webapp/media.py     图片压缩、视频抽帧、缩略图、拼图
webapp/store.py     本地任务库（SQLite WAL）
webapp/jobs.py      任务调度、并发、暂停 / 取消 / 重试
webapp/main.py      HTTP 接口
webapp/templates/   页面模板
webapp/static/      样式与前端脚本
build.bat           一键打包
build.py            打包脚本（含应用图标）
```

运行期数据保存在程序目录：`config.json`、`results.db`、`uploads/`、`输出/`。

---

## 本地数据与隐私

- API Key 只保存在本机 `config.json`，不会写入导出结果
- 前端不回显完整 Key；导出包不包含用户配置、素材和任务库
- 图片/视频只发送给你在设置中指定的模型接口，不经过额外中转
- 任务历史保存在本地 SQLite；删除 `results.db*` 只会清空历史，不影响已导出的文件

---

## 常见问题

**需要自己准备 API Key 吗？**

云端服务需要。工具不内置公共 Key，也不代充额度。使用 Ollama、LM Studio 等本机服务时，本机地址可免 Key。

**会上传我的素材到第三方吗？**

只会发送给你在设置中指定的模型服务商；工具本身不收集、不上传素材到其他服务器。

**为什么 Windows 会提示风险？**

PyInstaller 打包程序常见的误报。可添加信任，或直接使用源码版运行。

**批量出现 429 怎么办？**

把并发降到 1–2，重试次数调高；不同服务商的限流策略不同。

**视频处理很慢？**

确认设置中的“视频抽帧拼图”已开启；9 帧拼图通常比逐帧请求更省 token。

**日志文件过大？**

`app.log` 是滚动日志（10MB × 5 份），并已屏蔽断连异常刷屏。

**环境损坏怎么办？**

删掉 `.venv`，重新双击 `start_simple.bat` 自动重建。

---

## 从源码构建

环境要求：Python 3.10+，推荐 3.12。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

或直接双击 `build.bat`。构建后的免安装目录在 `dist\全能媒体反推\`，可直接压缩分发。

---

## English Overview

Omni Media Prompt Reverser is a local Windows tool for batch image-to-prompt and video-to-prompt conversion. It sends your images or sampled video frames to any vision LLM you configure, then produces structured, reusable prompts for AI art, video generation, e-commerce visuals and asset tagging.

Key features include 30 scene presets, 6 provider options, 1–8 concurrent workers, retry/resume, local SQLite history, and TXT/CSV/JSON/ZIP export. A portable Windows build is available via the Quark/Xunlei links above or GitHub Releases; no Python installation is required.

---

## License

Copyright © 2025–2026 AI绘画画. 授权方式以仓库根目录 `LICENSE` 文件为准。

