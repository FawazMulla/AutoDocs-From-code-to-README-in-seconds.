from flask import Flask, render_template, request, jsonify
import os
from core import ProjectScanner

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    path = data.get('path', '').strip()
    template = data.get('template', 'Detailed')
    
    if not path:
        return jsonify({"error": "Path is required"}), 400

    scanner = ProjectScanner(path)
    try:
        scanner.setup_path()
        scanner.scan()
        content = scanner.build_markdown(template)
        return jsonify({"success": True, "markdown": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        scanner.cleanup()

@app.route('/save', methods=['POST'])
def save_file():
    data = request.json
    path = data.get('path', '').strip()
    content = data.get('content')
    
    # Security: Only allow saving to local paths, not URLs
    if path.startswith('http') or path.endswith('.git'):
        return jsonify({"success": False, "error": "Cannot save directly to remote URL. Use Download button."})
        
    try:
        if not os.path.exists(path):
            return jsonify({"success": False, "error": "Directory does not exist."})
            
        with open(os.path.join(path, 'README.md'), 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    # Allow running on 0.0.0.0 for Docker compatibility
    app.run(host='0.0.0.0', port=5000, debug=True)