from flask import Flask, render_template, request, jsonify
import os
from core import generate_readme

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    path = data.get('path', '').strip()
    template = data.get('template', 'Detailed')
    # Capture the Custom Context from Frontend
    context = data.get('context', '').strip() 
    
    if not path:
        return jsonify({"success": False, "error": "Path is required"}), 400

    try:
        # Pass context to the core function
        content = generate_readme(path, template, context)
        return jsonify({"success": True, "markdown": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/save', methods=['POST'])
def save_file():
    data = request.json
    path = data.get('path', '').strip()
    content = data.get('content')
    
    if path.startswith('http') or path.endswith('.git'):
        return jsonify({"success": False, "error": "Remote repos cannot be saved locally. Use Download."})
        
    try:
        if not os.path.exists(path):
            return jsonify({"success": False, "error": "Directory not found"})
            
        with open(os.path.join(path, 'README.md'), 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)