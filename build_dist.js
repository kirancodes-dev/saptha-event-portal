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

console.log('Building dist directory for Zoho Slate deployer...');

// Ensure dist directory exists
if (fs.existsSync('dist')) {
    fs.rmSync('dist', { recursive: true, force: true });
}
fs.mkdirSync('dist', { recursive: true });

// Copy static assets
if (fs.existsSync('static')) {
    copyDirSync('static', path.join('dist', 'static'));
}

// Ensure index.html exists in dist
if (fs.existsSync('templates/public/home.html')) {
    fs.copyFileSync('templates/public/home.html', path.join('dist', 'index.html'));
} else {
    fs.writeFileSync(path.join('dist', 'index.html'), '<html><body><h1>SapthaEvent Portal</h1></body></html>');
}

console.log('Build completed successfully! dist/ directory generated for Zoho Slate.');
