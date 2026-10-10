## 网页拍摄

控制面板的“拍摄照片”按钮调用树莓派摄像头 0，拍摄后在页面显示照片。
默认使用 640×480 JPEG、质量 85，预热 1.5 秒，整个拍摄进程最多等待 20 秒。
照片返回网页前逆时针旋转 90°，完整保留画面，显示尺寸为 480×640。
照片直接传给浏览器，不保存到 SD 卡；刷新页面后预览清空。拍摄不会触发墨水屏刷新。

依赖系统命令 `rpicam-still`，不需要在 Python 虚拟环境中安装摄像头库。
可先在树莓派上检查：

```bash
command -v rpicam-still
rpicam-still --camera 0 --nopreview --timeout 1500 --width 640 --height 480 --output /tmp/camera-test.jpg
```

若命令缺失，可安装 `sudo apt install rpicam-apps`。
将更新后的 `server.py`、`templates/index.html`、`static/script.js` 和 `static/style.css`
同步到树莓派后，执行 `sudo systemctl restart epaper.service`，并强制刷新网页。
若拍摄失败，关闭正在使用摄像头的程序（例如 `rpicam-hello`），并查看日志：

```bash
journalctl -u epaper.service -n 50 --no-pager
```

摄像头参数说明：[Raspberry Pi 官方文档](https://www.raspberrypi.com/documentation/computers/camera_software.html)。

## 拍照后显示人脸相似度

参考照片为项目根目录下的 `ImageYF.png`，需要恰好有一张清晰人脸。
点击“拍摄照片”后，照片下方显示与参考人脸的余弦相似度（-1～1，越接近 1 越相似）和比对耗时。
这个分数不是身份正确的概率。未检测到人脸、多张人脸、缺少依赖或模型时会显示提示，仍保留拍摄照片。

### 安装和部署

同步以下内容到树莓派的 `/home/baoste/epaper2xl/`：

- `server.py`、`face_compare.py`、`prepare_face.py`、`requirements-face.txt`
- `templates/index.html`、`static/script.js`、`static/style.css`
- `ImageYF.png`
- 可选：已经下载好的 `models/` 和 `.face_cache/`（包含隐藏目录），避免树莓派再次下载和提取参考特征。

在树莓派上执行：

```bash
cd /home/baoste/epaper2xl
/home/baoste/epaper-env/bin/python -m pip install --only-binary=:all: -r requirements-face.txt
/home/baoste/epaper-env/bin/python prepare_face.py
sudo systemctl restart epaper.service
```

然后强制刷新网页。准备脚本从 OpenCV 官方仓库下载模型、核对 SHA-256，并保存参考特征到 `.face_cache/ImageYF.npz`。
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
- 第一次拍摄时加载模型，后续在同一服务进程中复用，仅提取新照片的人脸特征。
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
