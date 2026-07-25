const fs = require('fs');
const path = require('path');

function copyDirSync(src, dest) {
    if (!fs.existsSync(src)) return;
    fs.mkdirSync(dest, { recursive: true });
    let entries = fs.readdirSync(src, { withFileTypes: true });
    for (let entry of entries) {
        let srcPath = path.join(src, entry.name);
        let destPath = path.join(dest, entry.name);
        if (entry.isDirectory()) {
            copyDirSync(srcPath, destPath);
        } else {
            fs.copyFileSync(srcPath, destPath);
        }
    }
}

console.log('Building Slate production bundle...');

if (fs.existsSync('dist')) {
    fs.rmSync('dist', { recursive: true, force: true });
}
fs.mkdirSync('dist', { recursive: true });

if (fs.existsSync('static')) {
    copyDirSync('static', path.join('dist', 'static'));
}

if (fs.existsSync('templates/public/home.html')) {
    fs.copyFileSync('templates/public/home.html', path.join('dist', 'index.html'));
}

console.log('Slate production bundle ready in dist/');
