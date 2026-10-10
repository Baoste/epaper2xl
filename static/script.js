const captureBtn = document.getElementById("captureBtn");
const cameraMsg = document.getElementById("cameraMsg");
const cameraPreview = document.getElementById("cameraPreview");
const faceResult = document.getElementById("faceResult");
let photoUrl = null;

captureBtn.addEventListener("click", async () => {
  if (captureBtn.disabled) return;
  captureBtn.disabled = true;
  captureBtn.textContent = "正在拍摄并比对…";
  cameraMsg.textContent = "正在拍摄并比对，首次加载模型可能稍慢…";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  let nextUrl = null;
  try {
    const res = await fetch("/capture", { method: "POST", signal: controller.signal });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.message || `拍摄失败（HTTP ${res.status}）`);
    }
    if (!res.headers.get("Content-Type")?.startsWith("image/jpeg")) {
      throw new Error("服务未返回照片，请重试");
    }
    nextUrl = URL.createObjectURL(await res.blob());
    // 确认新照片能解码后再替换，拍摄失败时保留上一张。
    const photo = new Image();
    photo.src = nextUrl;
    await photo.decode();
    cameraPreview.src = nextUrl;
    cameraPreview.hidden = false;
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = nextUrl;
    nextUrl = null;
    let comparison;
    try {
      comparison = JSON.parse(res.headers.get("X-Face-Result") || "null");
    } catch {
      comparison = null;
    }
    faceResult.hidden = false;
    faceResult.textContent = comparison?.status === "ok" && Number.isFinite(comparison.similarity)
      ? `与参考照片的相似度：${comparison.similarity.toFixed(4)} · 比对耗时 ${(comparison.elapsed_ms / 1000).toFixed(2)} 秒`
      : (comparison?.message || "照片已拍摄，未取得比对结果");
    cameraMsg.textContent = `拍摄成功 · ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    cameraMsg.textContent = err.name === "AbortError"
      ? "请求超时，请稍后重试"
      : `❌ ${err.message}`;
  } finally {
    clearTimeout(timeout);
    if (nextUrl) URL.revokeObjectURL(nextUrl);
    captureBtn.disabled = false;
    captureBtn.textContent = "📷 拍摄照片";
  }
});

document.getElementById("uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const msgBox = document.getElementById("msg");
  msgBox.innerText = "⏳ 正在上传并处理...";
  msgBox.style.color = "white";

  try {
    const res = await fetch("/upload", {
      method: "POST",
      body: formData
    });

    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      msgBox.innerText = "⚠️ 服务返回异常：" + text.slice(0, 100);
      msgBox.style.color = "orange";
      return;
    }

    if (data.status === "ok") {
      msgBox.innerText = "✅ 成功：" + (data.message || "已显示！");
      msgBox.style.color = "green";
    } else {
      msgBox.innerText = "❌ 失败：" + (data.message || "未知错误");
      msgBox.style.color = "red";
    }
  } catch (err) {
    msgBox.innerText = "⚠️ 网络错误：" + err;
    msgBox.style.color = "orange";
  }
});

document.getElementById("shutdownBtn").addEventListener("click", async () => {
  if (!confirm("确定要关闭树莓派吗？")) return;
  document.getElementById("msg").innerText = "⚠️ 正在关机...";
  try {
    const res = await fetch("/shutdown", { method: "POST" });
    const data = await res.json();
    document.getElementById("msg").innerText = "💤 " + data.message;
  } catch (err) {
    document.getElementById("msg").innerText = "❌ 关机失败: " + err;
  }
});

document.getElementById("playMovie").addEventListener("click", async () => {
  const msg = document.getElementById("msg");
  msg.innerText = "🎬 正在启动电影播放...";
  try {
    const res = await fetch("/play_movie", { method: "POST" });
    const data = await res.json();
    msg.innerText = "🎞️ " + data.message;
  } catch (err) {
    msg.innerText = "❌ 播放失败: " + err;
  }
});
