_BROWSER_INIT_JS = """\
Object.defineProperty(navigator, 'webdriver', {get: () => false});

var _W = 1920, _H = 1080;
['width','availWidth'].forEach(function(k){
    Object.defineProperty(screen, k, {get: () => _W});
});
['height','availHeight'].forEach(function(k){
    Object.defineProperty(screen, k, {get: () => _H});
});
Object.defineProperty(screen, 'colorDepth', {get: () => 24});
Object.defineProperty(screen, 'pixelDepth', {get: () => 24});

Object.defineProperty(window, 'outerWidth',  {get: () => _W});
Object.defineProperty(window, 'outerHeight', {get: () => _H});
Object.defineProperty(window, 'innerWidth',  {get: () => _W});
Object.defineProperty(window, 'innerHeight', {get: () => _H - 80});
Object.defineProperty(window, 'devicePixelRatio', {get: () => 1});

if (!window.chrome) window.chrome = {};
if (!window.chrome.runtime) {
    window.chrome.runtime = {connect: function(){}, sendMessage: function(){}};
}
if (!window.chrome.app) window.chrome.app = {isInstalled: false};
"""
