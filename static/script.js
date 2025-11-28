let currentMd = "";

async function generate() {
    const path = document.getElementById('pathInput').value;
    const template = document.getElementById('templateInput').value;
    const btn = document.getElementById('genBtn');
    const status = document.getElementById('status');
    
    if(!path) return alert("Please enter a path or URL");
    
    btn.disabled = true;
    btn.innerText = "⏳ Scanning...";
    status.innerText = "Scanning project structure...";
    
    try {
        const res = await fetch('/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path, template})
        });
        const data = await res.json();
        
        if(data.success) {
            currentMd = data.markdown;
            document.getElementById('preview').innerHTML = marked.parse(data.markdown);
            mermaid.init(undefined, document.querySelectorAll('.mermaid'));
            status.innerText = "✅ Generated Successfully";
        } else {
            status.innerText = "❌ Error: " + data.error;
        }
    } catch(e) {
        status.innerText = "❌ Network Error";
    } finally {
        btn.disabled = false;
        btn.innerText = "✨ Generate";
    }
}

async function saveMd() {
    const path = document.getElementById('pathInput').value;
    if(!currentMd) return alert("Generate first!");
    
    const res = await fetch('/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path, content: currentMd})
    });
    const data = await res.json();
    if(data.success) alert("Saved README.md to folder!");
    else alert("Save failed: " + data.error);
}

function copyMd() {
    if(currentMd) {
        navigator.clipboard.writeText(currentMd);
        alert("Copied to clipboard!");
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