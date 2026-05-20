STEALTH_SCRIPT = """
// ====== 1. Xoá mọi dấu vết automation ======
Object.defineProperty(navigator, 'webdriver', { get: () => false });
delete navigator.__proto__.webdriver;

// ====== 2. Fake plugins ======
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Adobe Flash Player', filename: 'pepflashplayer.dll' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ],
});

// ====== 3. Fake WebGL vendor/renderer ======
const getParameterProxyHandler = {
    apply(target, ctx, args) {
        const param = args[0];
        if (param === 37445) return 'Intel Inc.';     // UNMASKED_VENDOR_WEBGL
        if (param === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
        return Reflect.apply(target, ctx, args);
    }
};
if (window.WebGLRenderingContext) {
    WebGLRenderingContext.prototype.getParameter = new Proxy(
        WebGLRenderingContext.prototype.getParameter,
        getParameterProxyHandler
    );
}
if (window.WebGL2RenderingContext) {
    WebGL2RenderingContext.prototype.getParameter = new Proxy(
        WebGL2RenderingContext.prototype.getParameter,
        getParameterProxyHandler
    );
}

// ====== 4. Fake AudioContext ======
if (AudioContext.prototype.hasOwnProperty('createOscillator')) {
    AudioContext.prototype.createOscillator = new Proxy(
        AudioContext.prototype.createOscillator,
        { apply() { return { connect(){} }; } }
    );
}

// ====== 5. Giả lập chrome object ======
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// ====== 6. Xoá CDC và các biến Playwright ======
setInterval(() => {
    for (const key of Object.keys(window)) {
        if (key.startsWith('cdc_') || key.startsWith('__playwright')) {
            try { delete window[key]; } catch(e) {}
        }
    }
}, 50);

// ====== 7. Screen resolution nhất quán ======
Object.defineProperty(screen, 'width', { value: screen.width, writable: false });
Object.defineProperty(screen, 'availWidth', { value: screen.availWidth, writable: false });

// ====== 8. timezone & language khớp với context ======
// (đã set trong browser.new_context)
"""