## 网页拍摄

控制面板的“拍摄照片”按钮调用树莓派摄像头 0，拍摄后在页面显示照片。
后台通过常驻的 `rpicam-vid` 以 2fps 采集 640×480 JPEG（质量 85），只保留最新画面，不积压帧。
摄像头首次开启预热至少 1.5 秒；每次请求等待一张新画面，最多等待 10 秒。摄像头保持打开不代表每帧都识别人脸。
照片返回网页前逆时针旋转 90°，再左右镜像，完整保留画面，显示尺寸为 480×640。人脸比对使用同一张镜像照片。
照片直接传给浏览器，不保存到 SD 卡；刷新页面后预览清空。拍摄不会触发墨水屏刷新。

依赖系统命令 `rpicam-vid`，不需要在 Python 虚拟环境中安装摄像头库。
可先在树莓派上检查（测试前停止服务，释放摄像头）：

```bash
command -v rpicam-vid
sudo systemctl stop epaper.service
rpicam-vid --camera 0 --nopreview --timeout 3000 --width 640 --height 480 --framerate 2 --codec mjpeg --output /tmp/camera-test.mjpeg
sudo systemctl start epaper.service
```

若命令缺失，可安装 `sudo apt install rpicam-apps`。
将更新后的 `server.py`、`camera_stream.py`、`presence_monitor.py`、`face_compare.py`、`templates/index.html`、`static/script.js` 和 `static/style.css`
同步到树莓派后，执行 `sudo systemctl restart epaper.service`，并强制刷新网页。
若拍摄失败，关闭正在使用摄像头的程序（例如 `rpicam-hello`），并查看日志：

```bash
journalctl -u epaper.service -n 50 --no-pager
```

摄像头参数说明：[Raspberry Pi 官方文档](https://www.raspberrypi.com/documentation/computers/camera_software.html)。

## 自动工位问候

### 二维状态切换表

只填写上三角：**→ 为行状态到列状态，← 为列状态到行状态**；`—` 表示无直接切换。首次／再次本人分别指当天未完成／已完成首次问候时识别到本人。

| 状态 | absent 无人（默认） | visitor 访客 | first 首次问候 | return 返回问候 | owner 在岗 | break 休息提醒 | rest 夜间休息 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| absent 无人（默认） | | → 连续 3 次低分；← 无人 | → 首次本人；← 无人 | → 再次本人；← 无人 | ← 连续无人超过 5 秒（每轮等 1 秒复查） | ← 无人 | → 22:00；← 08:00 |
| visitor 访客 | | | → 首次本人 | → 再次本人 | — | — | → 22:00 |
| first 首次问候 | | | | — | → 问候满 1 分钟 | — | → 22:00 |
| return 返回问候 | | | | | → 问候满 1 分钟 | — | → 22:00 |
| owner 在岗 | | | | | | → 在岗满 60 分钟；← 提醒满 5 分钟 | → 22:00 |
| break 休息提醒 | | | | | | | → 22:00 |
| rest 夜间休息 | | | | | | | |

计时从文案成功显示后开始；无人切换优先于计时到期，异常或多人保持当前状态。启动和 08:00 恢复时默认无人。
高分指相似度 ≥ 0.38，低分指 < 0.38；离开确认期间检测到人脸或异常会清零无人计时。夜间时间按 UTC+8。

### 状态文案与采集间隔

每次进入状态时，从 `presence_monitor.py` 的 `STATE_TEXTS` 中随机取一条；同一状态持续、离开确认或刷屏重试时沿用已选文案。再次进入会重新抽取，可能与上次相同。

| 状态 | 墨水屏行为 | 摄像机采集间隔（取帧检测） |
| --- | --- | --- |
| `absent` 无人（默认） | ① 这里是徐一帆的工位，目前不在哦~<br>② 一帆暂时不在工位～<br>③ 这里是一帆的工位／此刻无人，欢迎稍后来访 | 无人时 5 秒；出现低分人脸时 2 秒 |
| `visitor` 访客 | ① 欢迎来访，请稍候～<br>② 你好，欢迎来到一帆的工位！<br>③ 很高兴见到你／欢迎来访～ | 2 秒 |
| `first` 每日首次问候 | ① 你好，一帆！／新的一天，顺顺利利～<br>② 一帆，今天也请多关照～<br>③ 你好，一帆！／新的一天，从容开始 | 高分 60 秒；低分 2 秒 |
| `return` 返回问候 | ① 欢迎回来，一帆！<br>② 一帆，你回来啦～<br>③ 又见面啦，一帆！／继续自己的节奏吧 | 高分 60 秒；低分 2 秒 |
| `owner` 在岗 | ① 你好，一帆<br>② 一帆，按自己的节奏来～<br>③ 一帆，手边的事慢慢做好 | 高分 60 秒；低分 2 秒 |
| `owner` 离开确认中 | ① 你好，一帆<br>② 一帆，按自己的节奏来～<br>③ 一帆，手边的事慢慢做好 | 1 秒 |
| `break` 休息提醒 | ① 一帆，休息一下吧～／抬头远眺，活动肩膀<br>② 一帆，歇一小会儿／喝口水，看看远处<br>③ 忙了一阵啦，一帆／起身伸个懒腰吧～ | 高分 5 秒；低分 2 秒 |
| `rest` 夜间休息 | ① 夜深人静，休息中……<br>② 工位打烊啦／明天再见，晚安～<br>③ 今晚先休息／让忙碌留给明天吧 | 关闭摄像头，不采集 |

文案中的“／”表示换行。表中间隔为每轮处理结束后的检测等待时间；异常或多人时 5 秒后重试。白天摄像头实际以 2fps 常驻采集，临近文案计时或昼夜边界时会缩短等待。

## 拍照后显示人脸相似度

参考照片为项目目录下的 `imgs/head_photo.jpg`，需要恰好有一张清晰人脸。
点击“拍摄照片”后，照片下方显示与参考人脸的余弦相似度（-1～1，越接近 1 越相似）和比对耗时。
这个分数不是身份正确的概率。未检测到人脸、多张人脸、缺少依赖或模型时会显示提示，仍保留拍摄照片。

### 安装和部署

同步以下内容到树莓派的 `/home/baoste/epaper2xl/`：

- `server.py`、`camera_stream.py`、`presence_monitor.py`、`face_compare.py`、`prepare_face.py`、`requirements-face.txt`
- `templates/index.html`、`static/script.js`、`static/style.css`
- `imgs/head_photo.jpg`
- 可选：已经下载好的 `models/` 和 `.face_cache/`（包含隐藏目录），避免树莓派再次下载和提取参考特征。

在树莓派上执行：

```bash
cd /home/baoste/epaper2xl
/home/baoste/epaper-env/bin/python -m pip install --only-binary=:all: -r requirements-face.txt
/home/baoste/epaper-env/bin/python prepare_face.py
sudo systemctl restart epaper.service
```

然后强制刷新网页。准备脚本从 OpenCV 官方仓库下载模型、核对 SHA-256，并保存参考特征到 `.face_cache/head_photo.npz`。
如果这些文件已就绪，准备脚本会复用它们；正常拍摄和比对完全离线。
该缓存及模型目录已加入 `.gitignore`，通过 Git 更新代码时需要另外同步，或在树莓派运行准备脚本生成。

需要 OpenCV 4.8～4.x、NumPy 和 Pillow。若现有虚拟环境已经有兼容的 `cv2`，无需再安装另一种 OpenCV 包。
上面的安装命令只接受二进制包，避免在 Zero 2 W 上耗时编译。
如果提示没有兼容 wheel（例如某些 32 位系统），可检查系统软件源的 `python3-opencv` 版本；
只有版本达到 4.8 才能用于此模型，并且虚拟环境必须能访问系统包。
不要直接在 Zero 2 W 上启动 OpenCV 源码编译；需要匹配当前 Python/系统架构的预编译包，或使用 64 位 Raspberry Pi OS 的兼容 wheel。

### 减少每次比对开销

- YuNet 在固定 320×320 画布上检测，保留宽高比；关键点映射回原图后再对齐人脸。
- 使用约 9.9 MB 的 SFace INT8 模型，限制 OpenCV 使用 2 个线程。
- 参考特征持久缓存，照片或模型变化后自动重算；不要手动修改缓存内容。
- 服务启动后的第一次自动检测加载模型，后续在同一服务进程中复用，仅提取新照片的人脸特征。
- 同一时间只执行一次拍摄与比对，避免重复请求占用内存。实际耗时以树莓派网页显示为准。

模型来自 [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
和 [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface)。准备脚本同时下载模型目录中的许可证。

本地验证：`python -m unittest discover -s tests -v`。

## 打开关闭 systemd
```bash
# 开机自启
sudo systemctl enable epaper.service
# 开启/停止服务
sudo systemctl start epaper.service
sudo systemctl stop epaper.service
# 禁止开机自启
sudo systemctl disable epaper.service
# 查看状态
sudo systemctl status epaper.service
```

## 有办法将 http://192.168.1.25/ 改成好记的地址吗

**使用 mDNS**
也就是 .local 域名，例如：
http://raspberrypi.local/
http://epaper.local/

**操作步骤**
在树莓派安装 Avahi 服务（mDNS 解析器）
```bash
sudo apt install avahi-daemon -y
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon
```
修改主机名（比如改成 epaper2xl）
```bash
sudo hostnamectl set-hostname epaper2xl
```
重启 Avahi
```bash
sudo systemctl restart avahi-daemon
```
现在可以用：
http://epaper2xl.local/
访问网页（只要在同一个局域网内）。如果 Windows 无法访问 .local，安装 Bonjour。
