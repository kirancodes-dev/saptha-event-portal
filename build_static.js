const fs = require('fs');
const path = require('path');

// Helper to copy directory recursively
function copyDirSync(src, dest) {
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

console.log('Starting build for Slate static deployment...');

// Recreate dist
if (fs.existsSync('dist')) {
    console.log('Cleaning existing dist directory...');
    fs.rmSync('dist', { recursive: true, force: true });
}
fs.mkdirSync('dist', { recursive: true });

// Copy static directory content directly into dist/static
if (fs.existsSync('static')) {
    console.log('Copying static assets...');
    copyDirSync('static', path.join('dist', 'static'));
}

// Copy landing page as index.html
if (fs.existsSync('static_index.html')) {
    console.log('Copying static landing page...');
    fs.copyFileSync('static_index.html', path.join('dist', 'index.html'));
}

// Copy reports
if (fs.existsSync('SapthaEvent_Project_Report.html')) {
    console.log('Copying project report...');
    fs.copyFileSync('SapthaEvent_Project_Report.html', path.join('dist', 'SapthaEvent_Project_Report.html'));
}
if (fs.existsSync('MARKETING_REPORT.html')) {
    console.log('Copying marketing report...');
    fs.copyFileSync('MARKETING_REPORT.html', path.join('dist', 'MARKETING_REPORT.html'));
}

console.log('Build completed successfully! Files generated in "dist/".');
