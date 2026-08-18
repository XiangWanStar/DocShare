/* ═══════════════════════════════════════════════════════════════
   DocShare · 腾讯文档风格 SPA（真实后端）
   三栏布局: Rail(56px) + Sidebar(240px) + Main
   ═══════════════════════════════════════════════════════════════ */
const { createApp, reactive, computed, ref, onMounted, onUnmounted } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

/* ── API 层（真实后端） ─────────────────────────────────────── */
const API = {
  token() { return localStorage.getItem("docshare_token"); },
  setToken(t) { localStorage.setItem("docshare_token", t); },
  clearToken() { localStorage.removeItem("docshare_token"); },

  async request(path, { method = "GET", body } = {}) {
    const headers = {};
    const t = this.token();
    if (t) headers["Authorization"] = "Bearer " + t;
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    const resp = await fetch(path, { method, headers, body });
    if (resp.status === 401 && !path.startsWith("/api/auth/")) {
      this.clearToken();
      location.hash = "#/login";
      throw new Error("未登录或登录已过期");
    }
    if (resp.status === 204) return null;
    const ct = resp.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await resp.json() : await resp.text();
    if (!resp.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) detail = detail.map(d => d.msg).join("; ");
      throw new Error(typeof detail === "string" ? detail : "请求失败 (" + resp.status + ")");
    }
    return data;
  },

  get(path) { return this.request(path); },
  post(path, body) { return this.request(path, { method: "POST", body }); },
  del(path) { return this.request(path, { method: "DELETE" }); },

  async upload(path, file) {
    const fd = new FormData();
    fd.append("file", file);
    const headers = {};
    const t = this.token();
    if (t) headers["Authorization"] = "Bearer " + t;
    const resp = await fetch(path, { method: "POST", headers, body: fd });
    if (resp.status === 401) { this.clearToken(); location.hash = "#/login"; throw new Error("未登录"); }
    const ct = resp.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await resp.json() : await resp.text();
    if (!resp.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) detail = detail.map(d => d.msg).join("; ");
      throw new Error(typeof detail === "string" ? detail : "上传失败 (" + resp.status + ")");
    }
    return data;
  },
};

/* ── Store ───────────────────────────────────────────────────── */
const store = reactive({
  user: null,
  files: [],
  shares: [],
  currentFolder: "my",
  viewMode: "grid",
  loaded: false,
});

/* ── Helpers ─────────────────────────────────────────────────── */
function formatSize(b) {
  if (b == null) return "-";
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}
function formatTime(iso) {
  if (!iso) return "永久";
  const d = new Date(iso);
  if (isNaN(d)) return "-";
  const p = n => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fileExt(name) {
  const i = (name || "").lastIndexOf(".");
  return i > -1 ? "." + name.slice(i + 1).toLowerCase() : "";
}
const FILE_ICON_MAP = [
  { exts: [".doc", ".docx", ".docm", ".dot", ".dotx", ".dotm", ".rtf", ".odt", ".pages", ".epub"], icon: "word" },
  { exts: [".xls", ".xlsx", ".xlsm", ".xlt", ".xltx", ".csv", ".ods", ".ets"], icon: "excel" },
  { exts: [".ppt", ".pptx", ".pptm", ".pot", ".potx", ".pps", ".ppsx", ".odp"], icon: "ppt" },
  { exts: [".pdf", ".djvu", ".xps"], icon: "pdf" },
  { exts: [".txt", ".md", ".log", ".json", ".xml", ".yaml", ".yml"], icon: "txt" },
];
function fileIcon(name) {
  const ext = fileExt(name);
  for (const g of FILE_ICON_MAP) {
    if (g.exts.includes(ext)) return "/static/svg/" + g.icon + ".svg";
  }
  return "/static/svg/txt.svg";
}

/* ── SVG Icons ──────────────────────────────────────────────── */
const ICONS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>',
  edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  star: '<path d="M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"/>',
  grid: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/>',
  list: '<line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  folderOpen: '<path d="m6 14 1.5-2A7 7 0 0 1 12 10h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9L14.6 6h1.4a2 2 0 0 1 2 2v2"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  dots: '<path d="M5 12h.01M12 12h.01M19 12h.01"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  star2: '<path d="M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"/>',
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
};
function svgIcon(name, sz) {
  sz = sz || 16;
  const p = ICONS[name] || "";
  return '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + p + "</svg>";
}

/* ── OnlyOffice 工具 ─────────────────────────────────────────── */
// api.js 会把容器替换为 iframe（height:100% 相对 body 塌缩），这里显式撑满
function fitEditorIframe(offsetTop) {
  const ifr = document.querySelector('iframe[src*="web-apps"]');
  if (!ifr) return;
  const top = offsetTop || 0;
  ifr.style.width = "100%";
  ifr.style.height = Math.max(300, window.innerHeight - top) + "px";
  ifr.style.border = "0";
}
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error("无法加载 OnlyOffice 编辑器脚本（" + src + "），请确认 Document Server 已启动"));
    document.head.appendChild(s);
  });
}
function createEditor(elId, config, onReady, onError) {
  config.events = config.events || {};
  config.events.onDocumentReady = () => { if (onReady) onReady(); };
  config.events.onError = (err) => { if (onError) onError(err); };
  new DocsAPI.DocEditor(elId, config);
}

/* ── 全局确认对话框 ──────────────────────────────────────────── */
const confirmState = reactive({
  show: false, title: "", message: "", danger: false, resolve: null,
});

function confirmDialog(opts) {
  return new Promise(resolve => {
    confirmState.title = opts.title || "确认操作";
    confirmState.message = opts.message || "";
    confirmState.danger = !!opts.danger;
    confirmState.show = true;
    confirmState.resolve = resolve;
  });
}

const ConfirmDialog = {
  template: `
    <div class="modal-mask" v-if="confirmState.show" style="z-index:300">
      <div class="modal" style="max-width:400px">
        <div class="modal-header">
          <h3>{{ confirmState.title }}</h3>
          <button class="modal-close" @click="cancel" title="关闭"><span v-html="iconClose"></span></button>
        </div>
        <div class="modal-body">
          <p style="font-size:13px;line-height:1.8;color:var(--foreground);white-space:pre-wrap">{{ confirmState.message }}</p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="cancel" ref="cancelBtn">取消</button>
          <button class="btn" :class="confirmState.danger ? 'btn-danger-solid' : 'btn-primary'" @click="confirm">确定</button>
        </div>
      </div>
    </div>
  `,
  setup() { return { confirmState, iconClose: svgIcon("close", 16) }; },
  methods: {
    confirm() {
      confirmState.show = false;
      if (confirmState.resolve) confirmState.resolve(true);
    },
    cancel() {
      confirmState.show = false;
      if (confirmState.resolve) confirmState.resolve(false);
    },
  },
  mounted() {
    // 打开后聚焦取消按钮
    this.$nextTick(() => { const el = this.$refs.cancelBtn; if (el) el.focus(); });
  },
};

/* ═══════════════════════════════════════════════════════════════
   1. Login Component
   ═══════════════════════════════════════════════════════════════ */
const Login = {
  template: `
    <div class="login-page">
      <!-- ═══ 左侧品牌展示区 ═══ -->
      <aside class="login-hero">
        <div class="hero-bg"></div>
        <div class="hero-bg-deco icon-deco-1"><iconify-icon icon="mdi:file-document-outline" width="120"></iconify-icon></div>
        <div class="hero-bg-deco icon-deco-2"><iconify-icon icon="mdi:share-outline" width="80"></iconify-icon></div>
        <div class="hero-bg-deco icon-deco-3"><iconify-icon icon="mdi:lock-outline" width="60"></iconify-icon></div>
        <div class="hero-content">
          <div class="hero-brand">
            <div class="hero-logo"><iconify-icon icon="mdi:file-document-outline" width="20"></iconify-icon></div>
            <span class="hero-name">DocShare</span>
          </div>
          <div class="hero-middle">
            <div class="hero-tagline">
              <h2>文档协作<br>高效分享</h2>
              <p>上传、在线编辑、生成分享链接<br>一站式文档管理平台</p>
            </div>
            <div class="hero-features">
              <div class="hero-feat">
                <span class="feat-ic" v-html="iconFeatUpload"></span>
                <div><b>在线编辑</b><span>支持 Word / Excel / PPT 在线协作</span></div>
              </div>
              <div class="hero-feat">
                <span class="feat-ic" v-html="iconFeatShare"></span>
                <div><b>一键分享</b><span>生成链接，设权限、加密码、定时失效</span></div>
              </div>
              <div class="hero-feat">
                <span class="feat-ic" v-html="iconFeatLock"></span>
                <div><b>安全可控</b><span>权限管理 + 版本追踪，数据不外泄</span></div>
              </div>
            </div>
          </div>
          <div class="hero-bottom">
            <div class="hero-dots">
              <span class="active"></span><span></span><span></span>
            </div>
            <div class="hero-copy">© 2026 DocShare · 让文档协作更简单</div>
          </div>
        </div>
      </aside>

      <!-- ═══ 右侧表单区 ═══ -->
      <main class="login-form-area">
        <div class="login-form-card">
          <div class="login-form-header">
            <h1>欢迎回来</h1>
            <p>登录你的 DocShare 账号</p>
          </div>
          <div v-if="alert.show" :class="'alert alert-' + alert.type">{{ alert.msg }}</div>
          <form @submit.prevent="handleLogin" class="login-form">
            <div class="login-field">
              <label class="login-label">邮箱</label>
              <div class="login-input-wrap" :class="{ focus: focusField === 'email' }">
                <span class="login-input-icon" v-html="iconEmail"></span>
                <input type="email"
                  v-model="form.email" required
                  placeholder="you@example.com"
                  class="login-input"
                  @focus="focusField = 'email'"
                  @blur="focusField = ''">
              </div>
            </div>
            <div class="login-field">
              <label class="login-label">密码</label>
              <div class="login-input-wrap" :class="{ focus: focusField === 'password' }">
                <span class="login-input-icon" v-html="iconPw"></span>
                <input :type="showPw ? 'text' : 'password'"
                  v-model="form.password" required
                  placeholder="请输入密码"
                  class="login-input"
                  @focus="focusField = 'password'"
                  @blur="focusField = ''">
                <button type="button" class="pw-toggle" @click="showPw = !showPw" tabindex="-1">
                  <span v-html="showPw ? iconEyeOff : iconEye"></span>
                </button>
              </div>
            </div>
            <div class="login-row">
              <label class="login-remember">
                <input type="checkbox" v-model="remember"> <span>记住我</span>
              </label>
              <a href="#" class="login-forgot" @click.prevent>忘记密码？</a>
            </div>
            <button type="submit" class="login-submit" :disabled="loading">
              <span v-if="loading" class="login-spinner"></span>
              {{ loading ? '登录中…' : '登 录' }}
            </button>
          </form>
          <div class="login-divider"><span>或</span></div>
          <div class="login-oauth">
            <button class="oauth-btn" @click="oauth('wechat')">
              <span class="oauth-ic wechat"><iconify-icon icon="mdi:wechat" width="14"></iconify-icon></span> 微信登录
            </button>
            <button class="oauth-btn" @click="oauth('google')">
              <span class="oauth-ic google"><iconify-icon icon="mdi:google" width="14"></iconify-icon></span> Google
            </button>
          </div>
          <div class="login-footer">
            还没有账号？<a href="#" @click.prevent="$router.push('/register')">立即注册</a>
          </div>
        </div>
      </main>
    </div>
  `,
  data() {
    return {
      form: { email: "", password: "" },
      loading: false,
      alert: { show: false, type: "error", msg: "" },
      focusField: "",
      showPw: false,
      remember: true,
      iconFeatUpload: svgIcon("upload", 20),
      iconFeatShare: svgIcon("share", 20),
      iconFeatLock: svgIcon("lock", 20),
      iconEmail: svgIcon("mail", 18),
      iconPw: svgIcon("lock", 18),
      iconEye: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>',
      iconEyeOff: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg>',
    };
  },
  methods: {
    async handleLogin() {
      this.loading = true;
      try {
        const data = await API.post("/api/auth/login", this.form);
        API.setToken(data.access_token);
        this.$router.push("/dashboard");
      } catch (e) {
        this.alert = { show: true, type: "error", msg: e.message };
        this.loading = false;
      }
    },
    oauth(provider) {
      this.alert = { show: true, type: "info", msg: provider === "wechat" ? "微信登录（演示）" : "Google 登录（演示）" };
    },
  },
};

/* ═══════════════════════════════════════════════════════════════
   2. Register Component
   ═══════════════════════════════════════════════════════════════ */
const Register = {
  template: `
    <div class="auth-wrap">
      <div class="auth-card">
        <div class="auth-logo">
          <div class="icon"><iconify-icon icon="mdi:file-document-outline" width="24"></iconify-icon></div>
          <h1>注册账号</h1>
          <p>创建你的 DocShare 账号</p>
        </div>
        <div v-if="alert.show" :class="'alert alert-' + alert.type">{{ alert.msg }}</div>
        <form @submit.prevent="handleRegister">
          <div class="form-group">
            <input type="text" v-model="form.name" placeholder="昵称（可选）" class="form-input">
          </div>
          <div class="form-group">
            <input type="email" v-model="form.email" required placeholder="请输入邮箱" class="form-input">
          </div>
          <div class="form-group">
            <input type="password" v-model="form.password" required minlength="6" placeholder="设置密码（至少6位）" class="form-input">
          </div>
          <button type="submit" class="btn btn-primary btn-lg" style="width:100%" :disabled="loading">
            {{ loading ? '注册中…' : '注 册' }}
          </button>
        </form>
        <div class="auth-footer">已有账号？<a href="#" @click.prevent="$router.push('/login')">去登录</a></div>
      </div>
    </div>
  `,
  data() {
    return { form: { name: "", email: "", password: "" }, loading: false, alert: { show: false, type: "error", msg: "" } };
  },
  methods: {
    async handleRegister() {
      this.loading = true;
      try {
        const user = await API.post("/api/auth/register", {
          email: this.form.email, password: this.form.password, name: this.form.name || undefined,
        });
        // 注册成功后自动登录
        const data = await API.post("/api/auth/login", { email: user.email, password: this.form.password });
        API.setToken(data.access_token);
        this.$router.push("/dashboard");
      } catch (e) {
        this.alert = { show: true, type: "error", msg: e.message };
        this.loading = false;
      }
    },
  },
};

/* ═══════════════════════════════════════════════════════════════
   3. Dashboard Component — 腾讯文档三栏布局（真实数据）
   ═══════════════════════════════════════════════════════════════ */
const Dashboard = {
  template: `
    <div class="app-shell">
      <!-- ═══ Rail ═══ -->
      <aside class="rail">
        <div class="rail-logo"><iconify-icon icon="mdi:file-document-multiple-outline" width="18"></iconify-icon></div>
        <div class="rail-nav">
          <button class="rail-item" :class="{ active: store.currentFolder === 'my' }" @click="switchFolder('my')" title="我的文档">
            <span v-html="iconHome"></span>
          </button>
          <button class="rail-item" :class="{ active: store.currentFolder === 'starred' }" @click="switchFolder('starred')" title="收藏">
            <span v-html="iconStar"></span>
          </button>
          <button class="rail-item" :class="{ active: store.currentFolder === 'shared' }" @click="switchFolder('shared')" title="我分享的">
            <span v-html="iconUsers"></span>
          </button>
          <button class="rail-item" @click="openUploadModal" title="上传">
            <span v-html="iconUpload"></span>
          </button>
        </div>
      </aside>

      <!-- ═══ Sidebar ═══ -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="sidebar-search">
            <span v-html="iconSearch" style="color:var(--muted-foreground)"></span>
            <input v-model="searchQuery" placeholder="搜索文件">
          </div>
        </div>
        <div class="sidebar-tree">
          <div class="sidebar-section">文件库</div>
          <div class="tree-item" :class="{ active: store.currentFolder === 'my' }" @click="switchFolder('my')">
            <span v-html="iconFolder"></span>
            <span class="lbl">我的文档</span>
            <span class="count">{{ myCount }}</span>
          </div>
          <div class="tree-item" :class="{ active: store.currentFolder === 'starred' }" @click="switchFolder('starred')">
            <span v-html="iconStar"></span>
            <span class="lbl">收藏</span>
            <span class="count">{{ starredCount }}</span>
          </div>
          <div class="tree-item" :class="{ active: store.currentFolder === 'shared' }" @click="switchFolder('shared')">
            <span v-html="iconFolderOpen"></span>
            <span class="lbl">我分享的</span>
            <span class="count">{{ sharedCount }}</span>
          </div>

          <div class="sidebar-section" style="margin-top:8px">最近</div>
          <div v-for="f in recentFiles" :key="'r'+f.id" class="tree-item" @click="goViewer(f.id)">
            <span v-html="iconFile"></span>
            <span class="lbl">{{ f.filename }}</span>
          </div>
        </div>
      </aside>

      <!-- ═══ Main ═══ -->
      <main class="main-area">
        <div class="topbar">
          <div class="topbar-breadcrumb">
            <span class="crumb" @click="switchFolder('my')">文件库</span>
            <span class="sep">/</span>
            <span class="current">{{ folderLabel }}</span>
          </div>
          <div class="topbar-spacer"></div>
          <div class="topbar-search">
            <span v-html="iconSearch" style="color:var(--muted-foreground)"></span>
            <input v-model="searchQuery" placeholder="搜索">
          </div>
          <button class="btn-upload" @click="openUploadModal" title="上传文件">
            <span v-html="iconUpload" class="icon"></span>上传
          </button>
          <!-- ═══ 右上角个人用户信息 ═══ -->
          <div class="user-menu" v-if="store.user">
            <transition name="pop">
              <div class="user-popover" v-if="userMenuOpen" @click.stop>
                <div class="user-pop-header">
                  <div class="avatar">{{ (store.user.name || store.user.email || 'U')[0] }}</div>
                  <div class="info">
                    <div class="name">{{ store.user.name || '未设置昵称' }}</div>
                    <div class="email">{{ store.user.email }}</div>
                  </div>
                </div>
                <div class="user-pop-body">
                  <button class="user-menu-item" @click="logout">
                    <span v-html="iconLogout"></span>退出登录
                  </button>
                </div>
              </div>
            </transition>
            <button class="user-trigger" @click="userMenuOpen = !userMenuOpen" :title="store.user.name || store.user.email">
              {{ (store.user.name || store.user.email || 'U')[0] }}
            </button>
          </div>
        </div>

        <div class="content">
          <div v-if="alert.show" :class="'alert alert-' + alert.type">{{ alert.msg }}</div>

          <div class="action-bar">
            <div class="left">
              <span style="font-size:15px;font-weight:500">{{ folderLabel }}</span>
              <span style="color:var(--muted-foreground);font-size:12px">{{ filteredFiles.length }} 个文件</span>
            </div>
            <div class="right">
              <div class="view-toggle">
                <button :class="{ active: store.viewMode === 'grid' }" @click="store.viewMode = 'grid'" title="网格视图">
                  <span v-html="iconGrid"></span>
                </button>
                <button :class="{ active: store.viewMode === 'list' }" @click="store.viewMode = 'list'" title="列表视图">
                  <span v-html="iconList"></span>
                </button>
              </div>
            </div>
          </div>

          <!-- Grid View -->
          <div v-if="store.viewMode === 'grid'" class="file-grid">
            <div v-for="f in filteredFiles" :key="f.id" class="file-card" @click="goViewer(f.id)">
              <button class="star-btn" :class="{ on: f.starred }" @click.stop="toggleFav(f)" :title="f.starred ? '取消收藏' : '收藏'">
                <span v-html="iconStar"></span>
              </button>
              <div class="card-actions">
                <button class="card-act" @click.stop="downloadFile(f)" title="下载"><span v-html="iconDownload"></span></button>
                <button class="card-act" @click.stop="openShareModal(f)" title="分享"><span v-html="iconShare"></span></button>
                <button class="card-act" @click.stop="deleteFile(f)" title="删除"><span v-html="iconTrash"></span></button>
              </div>
              <img class="thumb" :src="fileIcon(f.filename)" alt="">
              <div class="name">{{ f.filename }}</div>
              <div class="meta">{{ formatSize(f.file_size) }} · v{{ f.version }}</div>
            </div>
          </div>

          <!-- List View -->
          <table v-else class="file-table">
            <thead>
              <tr><th></th><th>文件名</th><th>大小</th><th>版本</th><th>修改时间</th><th style="width:130px">操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="f in filteredFiles" :key="f.id" @click="goViewer(f.id)">
                <td style="width:34px">
                  <button class="star-btn" :class="{ on: f.starred }" @click.stop="toggleFav(f)" :title="f.starred ? '取消收藏' : '收藏'">
                    <span v-html="iconStar"></span>
                  </button>
                </td>
                <td><div class="fname"><img class="ic" :src="fileIcon(f.filename)" alt="">{{ f.filename }}</div></td>
                <td>{{ formatSize(f.file_size) }}</td>
                <td>v{{ f.version }}</td>
                <td>{{ formatTime(f.updated_at || f.created_at) }}</td>
                <td @click.stop>
                  <div class="table-ops">
                    <button class="btn btn-sm btn-ghost" @click="downloadFile(f)" title="下载"><span v-html="iconDownload" class="icon"></span></button>
                    <button class="btn btn-sm btn-ghost" @click="openShareModal(f)" title="分享"><span v-html="iconShare" class="icon"></span></button>
                    <button class="btn btn-sm btn-danger" @click="deleteFile(f)" title="删除"><span v-html="iconTrash" class="icon"></span></button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Empty -->
          <div v-if="!filteredFiles.length && !loading" class="empty">
            <div class="ic"><iconify-icon icon="mdi:folder-open-outline" width="40"></iconify-icon></div>
            <p>{{ folderLabel === '收藏' ? '还没有收藏的文档' : folderLabel === '我分享的' ? '还没有分享过文档' : '暂无文件，点击右上角上传' }}</p>
          </div>
          <div v-if="loading" class="empty"><div class="spinner"></div></div>

          <!-- Share Table -->
          <div style="margin-top:32px" v-if="store.shares.length">
            <div style="font-size:15px;font-weight:500;margin-bottom:12px">我的分享</div>
            <table class="file-table">
              <thead>
                <tr><th>文件名</th><th>权限</th><th>密码</th><th>有效期</th><th>分享链接</th><th style="width:80px">操作</th></tr>
              </thead>
              <tbody>
                <tr v-for="s in store.shares" :key="s.id">
                  <td>{{ s.filename }}</td>
                  <td><span :class="'badge ' + (s.permission === 'edit' ? 'badge-green' : 'badge-blue')">{{ s.permission === 'edit' ? '可编辑' : '只读' }}</span></td>
                  <td><span v-if="s.has_password" style="display:inline-flex;align-items:center;gap:3px"><iconify-icon icon="mdi:lock" width="13"></iconify-icon> 有</span><span v-else>—</span></td>
                  <td>{{ s.expires_at ? formatTime(s.expires_at) : '永久' }}</td>
                  <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><a :href="s.url" @click.prevent="copyShare(s.url)" :title="s.url">{{ s.url }}</a></td>
                  <td>
                    <div class="table-ops">
                      <button class="btn btn-sm btn-ghost" @click="copyShare(s.url)" title="复制"><span v-html="iconCopy"></span></button>
                      <button class="btn btn-sm btn-danger" @click="revokeShare(s)" title="撤销">撤销</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </main>

      <!-- ═══ Share Modal ═══ -->
      <div class="modal-mask" v-if="shareModal.show" @click.self="shareModal.show = false">
        <div class="modal">
          <div class="modal-header">
            <h3>创建分享链接</h3>
            <button class="modal-close" @click="shareModal.show = false"><span v-html="iconClose"></span></button>
          </div>
          <div class="modal-body">
            <div v-if="shareModal.alert" class="alert alert-error">{{ shareModal.alert }}</div>
            <div v-if="shareModal.created" class="alert alert-success">
              分享链接已生成：<br><a :href="shareModal.createdUrl" target="_blank" style="color:var(--primary);word-break:break-all">{{ shareModal.createdUrl }}</a>
              <div style="margin-top:8px"><button class="btn btn-sm btn-primary" @click="copyShare(shareModal.createdUrl)">复制链接</button></div>
            </div>
            <div class="form-group">
              <div class="form-label">文件名</div>
              <div style="font-size:13px;padding:4px 0">{{ shareModal.filename }}</div>
            </div>
            <div class="form-group">
              <div class="form-label">权限</div>
              <select v-model="shareModal.permission" class="form-select">
                <option value="view">只读</option>
                <option value="edit">可编辑</option>
              </select>
            </div>
            <div class="form-group">
              <div class="form-label">访问密码（可选）</div>
              <input type="text" v-model="shareModal.password" placeholder="留空则无需密码" class="form-input">
            </div>
            <div class="form-group">
              <div class="form-label">有效期（可选）</div>
              <input type="datetime-local" v-model="shareModal.expires" class="form-input">
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-ghost" @click="closeShareModal">关闭</button>
            <button class="btn btn-primary" @click="createShare" :disabled="shareModal.creating">{{ shareModal.creating ? '创建中…' : '创建' }}</button>
          </div>
        </div>
      </div>

      <!-- ═══ Upload Modal ═══ -->
      <div class="modal-mask" v-if="uploadModal.show" @click.self="closeUploadModal">
        <div class="modal upload-modal" style="max-width:520px">
          <div class="modal-header">
            <h3>上传文件</h3>
            <button class="modal-close" @click="closeUploadModal" title="关闭"><span v-html="iconClose"></span></button>
          </div>
          <div class="modal-body">
            <div class="upload-drop" :class="{ dragover: uploadModal.dragover }"
                 @click="$refs.uploadInput.click()"
                 @dragover.prevent="uploadModal.dragover = true"
                 @dragleave="uploadModal.dragover = false"
                 @drop.prevent="onDropFiles">
              <div class="ic"><iconify-icon icon="mdi:folder-upload-outline" width="30"></iconify-icon></div>
              <div><b>拖拽文件到此处</b>，或点击选择文件</div>
              <div class="hint">支持 .docx / .doc / .xlsx / .pptx / .pdf / .txt 等，单文件最大 50MB</div>
            </div>
            <input type="file" ref="uploadInput" multiple accept=".docx,.doc,.xlsx,.xls,.pptx,.ppt,.pdf,.txt,.odt,.rtf,.csv" style="display:none" @change="onPickFiles">

            <div v-if="uploadModal.files.length" class="upload-list">
              <div v-for="(item, i) in uploadModal.files" :key="i" class="upload-item">
                <img class="ext" :src="fileIcon(item.file.name)" alt="">
                <div class="fi">
                  <div class="fn">{{ item.file.name }}</div>
                  <div class="progress" v-if="item.status === 'uploading'">
                    <div class="bar" :style="{ width: item.progress + '%' }"></div>
                  </div>
                  <div class="st" :class="item.status">
                    <template v-if="item.status === 'uploading'">{{ item.progress }}%</template>
                    <template v-else-if="item.status === 'ok'"><span style="display:inline-flex;align-items:center;gap:2px"><iconify-icon icon="mdi:check-circle" width="13"></iconify-icon> 已上传</span></template>
                    <template v-else-if="item.status === 'fail'">{{ item.error || '上传失败' }}</template>
                    <template v-else>{{ formatSize(item.file.size) }}</template>
                  </div>
                </div>
                <button class="rm" v-if="item.status !== 'uploading' && item.status !== 'ok'" @click="removeUploadFile(i)" title="移除">×</button>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <span class="summary" v-if="uploadModal.uploading">正在上传 {{ uploadedCount }}/{{ uploadModal.files.length }}</span>
            <button class="btn btn-ghost" @click="closeUploadModal">{{ uploadModal.uploading ? '后台继续' : '关闭' }}</button>
            <button class="btn btn-primary" @click="startUpload" :disabled="!uploadModal.files.length || uploadModal.uploading">
              {{ uploadModal.uploading ? '上传中…' : '开始上传' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 拖拽上传层（全页拖拽打开模态框） -->
      <div class="dragover-layer" :class="{ show: dragOver }"><div class="tip">松开上传文件</div></div>

    </div>
  `,
  data() {
    return {
      store: store,
      searchQuery: "",
      alert: { show: false, type: "success", msg: "" },
      loading: true,
      dragOver: false,
      iconHome: svgIcon("home", 20),
      iconStar: svgIcon("star", 18),
      iconUsers: svgIcon("users", 20),
      iconShare: svgIcon("share", 20),
      iconUpload: svgIcon("upload", 20),
      iconSearch: svgIcon("search", 14),
      iconFolder: svgIcon("folder", 16),
      iconFolderOpen: svgIcon("folderOpen", 16),
      iconFile: svgIcon("file", 16),
      iconGrid: svgIcon("grid", 16),
      iconList: svgIcon("list", 16),
      iconDownload: svgIcon("download", 14),
      iconTrash: svgIcon("trash", 14),
      iconClose: svgIcon("close", 16),
      iconCopy: svgIcon("copy", 14),
      shareModal: {
        show: false, fileId: "", filename: "",
        permission: "view", password: "", expires: "", alert: "",
        creating: false, created: false, createdUrl: "",
      },
      userMenuOpen: false,
      iconLogout: svgIcon("logout", 15),
      uploadModal: {
        show: false, dragover: false, files: [], uploading: false,
      },
    };
  },
  computed: {
    myCount() { return this.store.files.length; },
    starredCount() { return this.store.files.filter(f => f.starred).length; },
    sharedCount() { return this.sharedFileIds.length; },
    sharedFileIds() {
      const ids = new Set();
      this.store.shares.forEach(s => ids.add(s.file_id));
      return Array.from(ids);
    },
    folderLabel() {
      const m = { my: "我的文档", starred: "收藏", shared: "我分享的" };
      return m[this.store.currentFolder] || "全部文件";
    },
    filteredFiles() {
      const folder = this.store.currentFolder;
      const q = this.searchQuery.toLowerCase();
      return this.store.files.filter(f => {
        if (folder === "starred" && !f.starred) return false;
        if (folder === "shared" && !this.sharedFileIds.includes(f.id)) return false;
        if (q && !f.filename.toLowerCase().includes(q)) return false;
        return true;
      });
    },
    recentFiles() {
      return this.store.files.slice(0, 4);
    },
    uploadedCount() {
      return this.uploadModal.files.filter(f => f.status === "ok").length;
    },
  },
  methods: {
    formatSize: formatSize,
    formatTime: formatTime,
    fileIcon: fileIcon,
    thumbBg(id) {
      const grads = [
        "linear-gradient(135deg,var(--chart-1),var(--chart-2))",
        "linear-gradient(135deg,var(--chart-2),var(--chart-3))",
        "linear-gradient(135deg,var(--green),var(--chart-2))",
        "linear-gradient(135deg,var(--orange),var(--destructive))",
      ];
      return grads[(parseInt(id, 36) || 0) % grads.length];
    },
    switchFolder(f) { this.store.currentFolder = f; },
    async loadAll() {
      this.loading = true;
      try {
        const [me, files, shares] = await Promise.all([
          API.get("/api/auth/me"),
          API.get("/api/files"),
          API.get("/api/shares"),
        ]);
        store.user = me;
        store.files = files;
        store.shares = shares;
      } catch (e) {
        this.showAlert(e.message, "error");
      } finally {
        this.loading = false;
      }
    },
    openUploadModal() {
      this.uploadModal.show = true;
      this.uploadModal.files = [];
      this.uploadModal.uploading = false;
      this.uploadModal.dragover = false;
    },
    closeUploadModal() {
      // 上传中允许后台继续
      this.uploadModal.show = false;
      if (!this.uploadModal.uploading) this.uploadModal.files = [];
    },
    onPickFiles(e) {
      this.addUploadFiles(Array.from(e.target.files || []));
      e.target.value = "";
    },
    onDropFiles(e) {
      this.uploadModal.dragover = false;
      this.addUploadFiles(Array.from(e.dataTransfer.files || []));
    },
    addUploadFiles(files) {
      const existing = new Set(this.uploadModal.files.map(x => x.file.name));
      files.forEach(f => {
        if (!existing.has(f.name)) {
          this.uploadModal.files.push({ file: f, status: "ready", progress: 0, error: "" });
          existing.add(f.name);
        }
      });
    },
    removeUploadFile(i) {
      this.uploadModal.files.splice(i, 1);
    },
    async startUpload() {
      if (this.uploadModal.uploading) return;
      this.uploadModal.uploading = true;
      let okCount = 0, failCount = 0;
      for (const item of this.uploadModal.files) {
        if (item.status === "ok" || item.status === "uploading") continue;
        item.status = "uploading";
        item.progress = 0;
        try {
          await this.uploadWithProgress(item.file, p => { item.progress = p; });
          item.status = "ok";
          item.progress = 100;
          okCount++;
        } catch (err) {
          item.status = "fail";
          item.error = err.message;
          failCount++;
        }
      }
      this.uploadModal.uploading = false;
      await this.loadAll();
      if (failCount === 0) {
        this.showAlert("成功上传 " + okCount + " 个文件", "success");
        setTimeout(() => { if (!this.uploadModal.uploading) this.uploadModal.show = false; }, 1200);
      } else if (okCount > 0) {
        this.showAlert("成功 " + okCount + " 个，失败 " + failCount + " 个", "error");
      } else {
        this.showAlert("上传失败", "error");
      }
    },
    uploadWithProgress(file, onProgress) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/files/upload");
        const t = API.token();
        if (t) xhr.setRequestHeader("Authorization", "Bearer " + t);
        xhr.upload.onprogress = e => {
          if (e.lengthComputable) onProgress(Math.round(e.loaded / e.total * 100));
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) { resolve(); return; }
          let msg = "上传失败 (" + xhr.status + ")";
          try {
            const d = JSON.parse(xhr.responseText);
            if (d && d.detail) msg = typeof d.detail === "string" ? d.detail : msg;
          } catch (e) { /* ignore */ }
          reject(new Error(msg));
        };
        xhr.onerror = () => reject(new Error("网络错误"));
        const fd = new FormData();
        fd.append("file", file);
        xhr.send(fd);
      });
    },
    async toggleFav(f) {
      try {
        const updated = await API.post("/api/files/" + f.id + "/star");
        f.starred = updated.starred;
        this.showAlert(updated.starred ? "已收藏「" + f.filename + "」" : "已取消收藏", "success");
      } catch (e) {
        this.showAlert(e.message, "error");
      }
    },
    downloadFile(f) {
      window.open(f.download_url || "/api/files/" + f.id + "/download", "_blank");
    },
    async deleteFile(f) {
      const ok = await confirmDialog({
        title: "删除文件",
        message: "确定删除「" + f.filename + "」？\n相关分享链接将一并失效，此操作不可恢复。",
        danger: true,
      });
      if (!ok) return;
      try {
        await API.del("/api/files/" + f.id);
        this.showAlert("文件已删除", "success");
        await this.loadAll();
      } catch (e) { this.showAlert(e.message, "error"); }
    },
    openShareModal(f) {
      this.shareModal = {
        show: true, fileId: f.id, filename: f.filename,
        permission: "view", password: "", expires: "", alert: "",
        creating: false, created: false, createdUrl: "",
      };
    },
    closeShareModal() { this.shareModal.show = false; },
    async createShare() {
      const m = this.shareModal;
      m.creating = true;
      m.alert = "";
      try {
        const data = await API.post("/api/shares", {
          file_id: m.fileId,
          permission: m.permission,
          password: m.password || undefined,
          expires_at: m.expires ? new Date(m.expires).toISOString() : undefined,
        });
        m.created = true;
        m.createdUrl = data.url;
        await this.loadAll();
      } catch (e) {
        m.alert = e.message;
      } finally {
        m.creating = false;
      }
    },
    copyShare(url) {
      navigator.clipboard.writeText(url).then(
        () => this.showAlert("链接已复制到剪贴板", "success"),
        () => this.showAlert("复制失败，请手动复制", "error")
      );
    },
    async revokeShare(s) {
      const ok = await confirmDialog({
        title: "撤销分享",
        message: "撤销后链接「" + s.url + "」将立即失效，确定要撤销吗？",
        danger: true,
      });
      if (!ok) return;
      try {
        await API.del("/api/shares/" + s.id);
        this.showAlert("分享已撤销", "success");
        await this.loadAll();
      } catch (e) { this.showAlert(e.message, "error"); }
    },
    goViewer(id) { this.$router.push({ path: "/viewer", query: { file_id: id } }); },
    async logout() {
      const ok = await confirmDialog({
        title: "退出登录",
        message: "确定要退出当前账号吗？",
      });
      if (!ok) return;
      this.userMenuOpen = false;
      API.clearToken();
      store.user = null;
      this.$router.push("/login");
    },
    showAlert(msg, type) {
      this.alert.show = true; this.alert.msg = msg; this.alert.type = type || "info";
      const self = this;
      setTimeout(() => { self.alert.show = false; }, 3500);
    },
    onDragOver(e) { e.preventDefault(); this.dragOver = true; },
    onDragLeave() { this.dragOver = false; },
    onDrop(e) {
      e.preventDefault();
      this.dragOver = false;
      const files = Array.from(e.dataTransfer.files || []);
      if (!files.length) return;
      if (!this.uploadModal.show) this.openUploadModal();
      this.addUploadFiles(files);
    },
  },
  mounted() {
    this.loadAll();
    window.addEventListener("dragover", this.onDragOver);
    window.addEventListener("dragleave", this.onDragLeave);
    window.addEventListener("drop", this.onDrop);
  },
  beforeUnmount() {
    window.removeEventListener("dragover", this.onDragOver);
    window.removeEventListener("dragleave", this.onDragLeave);
    window.removeEventListener("drop", this.onDrop);
  },
};


/* ═══════════════════════════════════════════════════════════════
   4. Viewer Component — OnlyOffice 在线查看/编辑（真实）
   ═══════════════════════════════════════════════════════════════ */
const Viewer = {
  template: `
    <div>
      <div class="viewer-bar">
        <button class="back-btn" @click="$router.push('/dashboard')" title="返回"><span v-html="iconBack"></span></button>
        <div class="title">{{ file ? file.filename : '加载中…' }}<span class="ver" v-if="file">v{{ file.version }}</span></div>
        <div class="spacer"></div>
        <button class="btn btn-sm btn-outline" @click="openShare" v-if="file"><span v-html="iconShare" class="icon"></span>分享</button>
        <button class="btn btn-sm btn-outline" @click="download" v-if="file"><span v-html="iconDownload" class="icon"></span>下载</button>
      </div>

      <!-- 加载中 -->
      <div v-if="state === 'loading'" class="editor-loading">
        <div class="spinner"></div>
        <div>正在启动 OnlyOffice 编辑器…</div>
        <div class="editor-hint" v-if="hint">首次打开需转换文档，可能较慢，若长时间无响应请重试</div>
        <button v-if="hint" class="btn btn-sm btn-outline" @click="init()">重 试</button>
      </div>

      <!-- 错误 -->
      <div v-else-if="state === 'error'" class="editor-error">
        <div class="alert alert-error">{{ errorMsg }}</div>
        <button class="btn btn-sm btn-primary" @click="init()">重 试</button>
      </div>

      <!-- 编辑器容器（api.js 会替换此元素为 iframe） -->
      <div v-else id="editor-container"></div>

      <!-- 分享模态框 -->
      <div class="modal-mask" v-if="shareModal.show" @click.self="shareModal.show = false">
        <div class="modal">
          <div class="modal-header">
            <h3>创建分享链接</h3>
            <button class="modal-close" @click="shareModal.show = false"><span v-html="iconClose"></span></button>
          </div>
          <div class="modal-body">
            <div v-if="shareModal.alert" class="alert alert-error">{{ shareModal.alert }}</div>
            <div v-if="shareModal.created" class="alert alert-success">
              分享链接已生成：<br><a :href="shareModal.createdUrl" target="_blank" style="color:var(--primary);word-break:break-all">{{ shareModal.createdUrl }}</a>
              <div style="margin-top:8px"><button class="btn btn-sm btn-primary" @click="copyLink(shareModal.createdUrl)">复制链接</button></div>
            </div>
            <div class="form-group">
              <div class="form-label">权限</div>
              <select v-model="shareModal.permission" class="form-select">
                <option value="view">只读</option>
                <option value="edit">可编辑</option>
              </select>
            </div>
            <div class="form-group">
              <div class="form-label">访问密码（可选）</div>
              <input type="text" v-model="shareModal.password" placeholder="留空则无需密码" class="form-input">
            </div>
            <div class="form-group">
              <div class="form-label">有效期（可选）</div>
              <input type="datetime-local" v-model="shareModal.expires" class="form-input">
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-ghost" @click="shareModal.show = false">关闭</button>
            <button class="btn btn-primary" @click="createShare" :disabled="shareModal.creating">{{ shareModal.creating ? '创建中…' : '创建' }}</button>
          </div>
        </div>
      </div>
    </div>
  `,
  data() {
    return {
      file: null,
      state: "loading",   // loading | ready | error
      errorMsg: "",
      hint: false,
      iconBack: svgIcon("back", 18),
      iconShare: svgIcon("share", 14),
      iconDownload: svgIcon("download", 14),
      iconClose: svgIcon("close", 16),
      shareModal: { show: false, permission: "view", password: "", expires: "", alert: "", creating: false, created: false, createdUrl: "" },
    };
  },
  methods: {
    async init() {
      const fid = this.$route.query.file_id;
      if (!fid) { this.state = "error"; this.errorMsg = "缺少文件参数"; return; }
      this.state = "loading";
      this.hint = false;
      this.errorMsg = "";
      // 45s 无就绪则提示
      this.hintTimer = setTimeout(() => { if (this.state === "loading") this.hint = true; }, 45000);
      try {
        this.file = await API.get("/api/files/" + fid);
        document.title = this.file.filename + " - DocShare";
        const data = await API.get("/api/office/config/" + fid);
        await loadScript(data.onlyofficeUrl + "/web-apps/apps/api/documents/api.js");
        this.state = "ready";
        this.$nextTick(() => {
          createEditor("editor-container", data.config,
            () => { clearTimeout(this.hintTimer); this.hint = false; },
            (err) => { this.state = "error"; this.errorMsg = "编辑器出错：" + ((err && err.description) || JSON.stringify(err)); }
          );
          fitEditorIframe(44);
        });
      } catch (e) {
        clearTimeout(this.hintTimer);
        this.state = "error";
        this.errorMsg = e.message;
      }
    },
    openShare() { this.shareModal.show = true; this.shareModal.permission = "view"; this.shareModal.password = ""; this.shareModal.expires = ""; this.shareModal.alert = ""; this.shareModal.created = false; },
    async createShare() {
      const m = this.shareModal;
      m.creating = true; m.alert = "";
      try {
        const data = await API.post("/api/shares", {
          file_id: this.file.id,
          permission: m.permission,
          password: m.password || undefined,
          expires_at: m.expires ? new Date(m.expires).toISOString() : undefined,
        });
        m.created = true; m.createdUrl = data.url;
      } catch (e) { m.alert = e.message; }
      finally { m.creating = false; }
    },
    copyLink(url) {
      navigator.clipboard.writeText(url).then(() => {}, () => {});
    },
    download() { window.open(this.file.download_url || "/api/files/" + this.file.id + "/download", "_blank"); },
    onResize() { if (this.state === "ready") fitEditorIframe(44); },
  },
  mounted() { this.init(); window.addEventListener("resize", this.onResize); },
  beforeUnmount() {
    window.removeEventListener("resize", this.onResize);
    clearTimeout(this.hintTimer);
  },
};

/* =============================================================
   5. Share Component - share landing (real)
   ============================================================= */
const ShareLanding = {
  template: `
    <div>
      <div class="share-wrap" v-if="!editorOpen">
        <div class="share-card">
          <div class="share-card-header" v-if="info.loaded">
            <div class="file-icon">📄</div>
            <h2>{{ info.filename }}</h2>
            <p>{{ formatSize(info.file_size) }} · {{ info.permission === 'edit' ? '可编辑' : '只读' }}<template v-if="info.owner_name"> · 由 {{ info.owner_name }} 分享</template></p>
          </div>
          <div class="share-card-header" v-if="loading">
            <div class="spinner" style="margin-bottom:12px"></div>
            <p>加载中…</p>
          </div>
          <div class="share-card-header" v-if="error.show">
            <div class="file-icon" style="background:#fee2e2">⚠️</div>
            <h2>{{ error.title }}</h2>
            <p>{{ error.msg }}</p>
          </div>
          <div class="share-card-body" v-if="needPassword && info.loaded">
            <div v-if="pwAlert" class="alert alert-error">{{ pwAlert }}</div>
            <div class="form-group">
              <div class="form-label">请输入访问密码</div>
              <input type="password" v-model="password" class="form-input" placeholder="访问密码" @keyup.enter="verifyPassword">
            </div>
            <button class="btn btn-primary btn-lg" style="width:100%" @click="verifyPassword" :disabled="verifying">{{ verifying ? '验证中…' : '进入查看' }}</button>
          </div>
        </div>
      </div>
      <div v-else class="share-editor">
        <a class="share-back" href="/" style="font-size:12px;color:var(--muted-foreground)">← DocShare</a>
        <div id="share-editor"></div>
      </div>
    </div>
  `,
  data() {
    return {
      token: "",
      info: { loaded: false, filename: "", file_size: null, permission: "view", owner_name: "" },
      needPassword: false,
      password: "",
      pwAlert: "",
      verifying: false,
      loading: true,
      error: { show: false, title: "", msg: "" },
      editorOpen: false,
      editorState: "loading",
      editorError: "",
      hint: false,
    };
  },
  methods: {
    formatSize: formatSize,
    async init() {
      this.loading = true;
      this.error.show = false;
      try {
        const info = await API.get("/s/" + this.token + "/info");
        if (!info.valid) {
          this.loading = false;
          this.error = { show: true, title: info.expired ? "分享链接已过期" : "无法访问", msg: info.message || "该分享不存在或已被撤销" };
          return;
        }
        this.info = { loaded: true, filename: info.filename, file_size: info.file_size, permission: info.permission, owner_name: info.owner_name };
        this.loading = false;
        if (info.requires_password) {
          this.needPassword = true;
        } else {
          try {
            const data = await API.post("/s/" + this.token + "/verify", {});
            this.openEditor(data.access_token);
          } catch (e) {
            this.error = { show: true, title: "加载失败", msg: e.message };
          }
        }
      } catch (e) {
        this.loading = false;
        this.error = { show: true, title: "加载失败", msg: e.message };
      }
    },
    async verifyPassword() {
      if (!this.password) { this.pwAlert = "请输入访问密码"; return; }
      this.verifying = true;
      this.pwAlert = "";
      try {
        const data = await API.post("/s/" + this.token + "/verify", { password: this.password });
        this.openEditor(data.access_token);
      } catch (e) {
        this.pwAlert = e.message;
      } finally {
        this.verifying = false;
      }
    },
    async openEditor(accessToken) {
      this.editorOpen = true;
      this.editorState = "loading";
      this.hint = false;
      this.hintTimer = setTimeout(() => { if (this.editorState === "loading") this.hint = true; }, 45000);
      try {
        const resp = await fetch("/api/office/share/" + this.token, {
          headers: accessToken ? { Authorization: "Bearer " + accessToken } : {},
        });
        if (resp.status === 503) { this.editorFail("OnlyOffice Document Server 未配置"); return; }
        if (!resp.ok) {
          const d = await resp.json().catch(() => ({}));
          this.editorFail((d && d.detail) || "无法打开文档，请重新验证");
          return;
        }
        const data = await resp.json();
        await loadScript(data.onlyofficeUrl + "/web-apps/apps/api/documents/api.js");
        this.editorState = "ready";
        this.$nextTick(() => {
          createEditor("share-editor", data.config,
            () => { clearTimeout(this.hintTimer); this.hint = false; document.title = this.info.filename + " - DocShare"; },
            (err) => this.editorFail("编辑器出错：" + ((err && err.description) || JSON.stringify(err)))
          );
          fitEditorIframe(0);
        });
      } catch (e) {
        this.editorFail(e.message);
      }
    },
    editorFail(msg) {
      clearTimeout(this.hintTimer);
      this.editorState = "error";
      this.editorError = msg;
      this.editorOpen = false;
      this.error = { show: true, title: "无法在线预览", msg: msg };
    },
    onResize() { if (this.editorState === "ready") fitEditorIframe(0); },
  },
  mounted() {
    this.token = this.$route.params.token || "";
    if (!this.token) {
      this.loading = false;
      this.error = { show: true, title: "链接无效", msg: "缺少分享标识" };
      return;
    }
    this.init();
    window.addEventListener("resize", this.onResize);
  },
  beforeUnmount() {
    window.removeEventListener("resize", this.onResize);
    clearTimeout(this.hintTimer);
  },
};

/* =============================================================
   Router
   ============================================================= */
const routes = [
  { path: "/", redirect: "/dashboard" },
  { path: "/login", component: Login },
  { path: "/register", component: Register },
  { path: "/dashboard", component: Dashboard },
  { path: "/viewer", component: Viewer },
  { path: "/share/:token", component: ShareLanding },
];

const router = createRouter({ history: createWebHashHistory(), routes });

router.beforeEach((to, from, next) => {
  const authed = !!API.token();
  if ((to.path === "/dashboard" || to.path === "/viewer") && !authed) next("/login");
  else if ((to.path === "/login" || to.path === "/register") && authed) next("/dashboard");
  else next();
});

const app = createApp({});
app.component("confirm-dialog", ConfirmDialog);
app.use(router);
app.mount("#app");