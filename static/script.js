let currentTemplate = 'Detailed';
let currentMd = '';

function setTemplate(mode, btn) {
    currentTemplate = mode;
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
}

function log(msg) {
    const term = document.getElementById('terminalLog');
    term.innerHTML += `> ${msg}<br>`;
    term.scrollTop = term.scrollHeight;
}

async function generate() {
    const path = document.getElementById('pathInput').value;
    // GET THE CUSTOM TEXT
    const context = document.getElementById('customContext').value; 
    const btn = document.getElementById('genBtn');
    
    if(!path) return alert("Please enter a path.");

    btn.disabled = true;
    btn.innerHTML = `<span class="loader"></span> Scanning...`;
    document.getElementById('terminalLog').innerHTML = '';
    log(`Target: ${path}`);
    log("Analyzing architecture & dependencies...");

    try {
        const res = await fetch('/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                path: path, 
                template: currentTemplate,
                context: context // SEND IT TO SERVER
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            log("Generating diagrams...");
            log("<span style='color:#4ade80'>Success!</span>");
            
            currentMd = data.markdown;
            document.getElementById('preview').innerHTML = marked.parse(data.markdown);
            mermaid.init(undefined, document.querySelectorAll('.mermaid'));
        } else {
            log(`<span style='color:#f87171'>Error: ${data.error}</span>`);
        }
    } catch (e) {
        log(`<span style='color:#f87171'>Network Error: ${e}</span>`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>🚀</span> Generate Docs`;
    }
}

async function saveMd() {
    const path = document.getElementById('pathInput').value;
    if(!currentMd) return alert("Nothing to save.");
    
    const res = await fetch('/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path, content: currentMd})
    });
    const data = await res.json();
    if(data.success) alert("Saved successfully!");
    else alert("Error: " + data.error);
}

function copyMd() {
    if(currentMd) {
        navigator.clipboard.writeText(currentMd);
        log("Copied to clipboard.");
    }
}

function downloadMd() {
    if(!currentMd) return;
    const blob = new Blob([currentMd], {type: 'text/markdown'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'README.md';
    a.click();
}