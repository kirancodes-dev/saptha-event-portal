const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

console.log('Building Slate production bundle with Flask Jinja pre-rendering...');

let rendered = false;
const pythonBins = ['./.venv/bin/python', 'python3', 'python'];

for (const py of pythonBins) {
    try {
        if (fs.existsSync(py) || py !== './.venv/bin/python') {
            console.log(`Trying pre-render with ${py}...`);
            execSync(`${py} build_dist.py`, { stdio: 'inherit' });
            rendered = true;
            console.log('✅ Flask pre-rendering succeeded!');
            break;
        }
    } catch (err) {
        // Try next python binary
    }
}

if (!rendered) {
    console.log('⚠️ Fallback to static copy build');
    if (!fs.existsSync('dist')) {
        fs.mkdirSync('dist', { recursive: true });
    }
    if (fs.existsSync('templates/public/home.html')) {
        fs.copyFileSync('templates/public/home.html', path.join('dist', 'index.html'));
    }
}

if (!fs.existsSync(path.join('dist', 'static')) && fs.existsSync('static')) {
    fs.cpSync('static', path.join('dist', 'static'), { recursive: true });
}

console.log('Slate production bundle ready in dist/');
