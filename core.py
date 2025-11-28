import os
import json
import shutil
import git
import tempfile
import re
import stat
import ast

# --- CONFIGURATION ---
STD_LIBS = {
    'python': {'os', 'sys', 're', 'json', 'math', 'datetime', 'time', 'random', 'subprocess', 'typing', 'collections', 'threading', 'asyncio', 'logging'},
    'node': {'fs', 'path', 'http', 'https', 'os', 'util', 'events', 'crypto', 'child_process', 'cluster', 'dns', 'net', 'stream'}
}

IGNORE_DIRS = {'.git', 'node_modules', 'venv', '.env', '__pycache__', 'dist', 'build', 'target', 'vendor', '.idea', '.vscode', 'coverage', '.next', '__mocks__'}

class DeepScanner:
    def __init__(self, path, custom_context=""):
        self.original_path = path
        self.path = path
        self.custom_context = custom_context
        self.is_remote = path.startswith('http') or path.endswith('.git')
        self.temp_dir = None
        self.metadata = {
            "project_name": "",
            "username": "username", # For badges
            "repo_name": "repo",    # For badges
            "languages": set(),
            "tech_stack": set(),
            "dependencies": {"Python": set(), "Node.js": set(), "Go": set()},
            "scripts": {},
            "structure": "",
            "description": "",
            "entry_point": None,
            "api_endpoints": [],
            "license": "Unlicensed",
            "modules": [],
            "flow": [],
            "env_vars": set(), # NEW: Stores detected environment variables
            "tests": []        # NEW: Stores detected test frameworks
        }

    def setup_path(self):
        if self.is_remote:
            self.temp_dir = tempfile.mkdtemp()
            try:
                git.Repo.clone_from(self.original_path, self.temp_dir)
                self.path = self.temp_dir
                
                # Extract Git Info for Badges
                parts = self.original_path.rstrip('/').split('/')
                if len(parts) >= 2:
                    self.metadata["repo_name"] = parts[-1].replace('.git', '')
                    self.metadata["username"] = parts[-2]
                    self.metadata["project_name"] = self.metadata["repo_name"]
            except Exception as e:
                self.cleanup()
                raise Exception(f"Clone failed: {str(e)}")
        else:
            if not os.path.exists(self.path):
                raise Exception("Local path does not exist.")
            self.metadata["project_name"] = os.path.basename(os.path.normpath(self.path))
            
            # Try to read local git config for badges
            try:
                repo = git.Repo(self.path)
                url = repo.remotes.origin.url
                parts = url.rstrip('/').replace('.git', '').split('/')
                self.metadata["repo_name"] = parts[-1]
                self.metadata["username"] = parts[-2].split(':')[-1] # Handle git@github.com:user/repo
            except: pass

        return self.path

    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                def on_rm_error(func, path, exc_info):
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                shutil.rmtree(self.temp_dir, onerror=on_rm_error)
            except: pass

    def scan(self):
        self._scan_license()
        self._scan_tree(self.path)
        if not self.metadata["description"]:
            self.metadata["description"] = self._generate_smart_description()
        return self.metadata

    def _generate_smart_description(self):
        name = self.metadata["project_name"].replace('-', ' ').replace('_', ' ').title()
        langs = list(self.metadata["languages"])
        stack = list(self.metadata["tech_stack"])
        
        ptype = "Application"
        if "Api" in name: ptype = "RESTful API"
        elif "Web" in name: ptype = "Web Platform"
        elif "Lib" in name: ptype = "Library"
        
        framework = ""
        for t in stack:
            if "Framework" in t: framework = t.split(': ')[1]; break
        
        desc = f"**{name}** is a robust {ptype}"
        if framework: desc += f" built with **{framework}**"
        elif langs: desc += f" built using **{langs[0]}**"
        desc += "."
        return desc

    def _scan_license(self):
        for f in os.listdir(self.path):
            if f.upper().startswith('LICENSE') or f.upper().startswith('COPYING'):
                try:
                    with open(os.path.join(self.path, f), 'r') as lic_file:
                        content = lic_file.read(100).upper()
                        if "MIT" in content: self.metadata["license"] = "MIT"
                        elif "APACHE" in content: self.metadata["license"] = "Apache 2.0"
                        elif "GNU" in content or "GPL" in content: self.metadata["license"] = "GPL"
                        else: self.metadata["license"] = "See LICENSE file"
                except: pass
                break

    def _scan_tree(self, root_path):
        tree_lines = []
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            rel_path = os.path.relpath(root, root_path)
            
            level = rel_path.count(os.sep)
            if rel_path == '.': level = 0
            else: level += 1

            if level < 3:
                indent = '│   ' * level
                subindent = '├── '
                if level > 0: tree_lines.append(f"{indent}{subindent}{os.path.basename(root)}/")
                for f in files:
                    if not f.startswith('.'): tree_lines.append(f"{indent}│   {f}")

            for f in files:
                filepath = os.path.join(root, f)
                ext = os.path.splitext(f)[1]
                
                if f == 'package.json':
                    self.metadata["languages"].add("Node.js")
                    self._parse_package_json(filepath)
                elif f == 'requirements.txt':
                    self.metadata["languages"].add("Python")
                    self._parse_requirements(filepath)
                elif f == 'go.mod': self.metadata["languages"].add("Go")
                elif f == 'pom.xml': self.metadata["languages"].add("Java")
                elif f == 'Dockerfile': self.metadata["tech_stack"].add("DevOps: Docker")

                if ext in ['.py', '.js', '.ts', '.jsx', '.go']:
                    self._analyze_code(filepath, ext)

        self.metadata["structure"] = "```text\n.\n" + "\n".join(tree_lines) + "\n```"

    def _parse_package_json(self, filepath):
        try:
            with open(filepath) as f:
                data = json.load(f)
                if data.get('name'): self.metadata["project_name"] = data.get('name')
                deps = list(data.get('dependencies', {}).keys())
                devDeps = list(data.get('devDependencies', {}).keys())
                
                self.metadata["dependencies"]["Node.js"].update(deps)
                self.metadata["scripts"] = data.get('scripts', {})
                if data.get('description'): self.metadata["description"] = data.get('description')
                
                # Check for Test Frameworks
                for d in deps + devDeps:
                    if d in ['jest', 'mocha', 'chai', 'supertest']:
                        self.metadata["tests"].append(d)
        except: pass

    def _parse_requirements(self, filepath):
        try:
            with open(filepath) as f:
                deps = [line.split('==')[0].split('>=')[0].strip() for line in f if line.strip() and not line.startswith('#')]
                self.metadata["dependencies"]["Python"].update(deps)
                # Check for Test Frameworks
                for d in deps:
                    if d in ['pytest', 'unittest', 'nose']: self.metadata["tests"].append(d)
        except: pass

    def _analyze_code(self, filepath, ext):
        try:
            with open(filepath, 'r', errors='ignore', encoding='utf-8') as f:
                content = f.read()

                # Entry Point
                if "app.listen" in content or "run(host=" in content or 'if __name__ == "__main__":' in content:
                    self.metadata["entry_point"] = os.path.basename(filepath)

                # Environment Variables Scanning (Regex)
                # Matches: process.env.API_KEY or os.environ['DB_PASS'] or os.getenv('HOST')
                env_matches = re.findall(r'(?:process\.env\.|os\.environ\.get\([\'"]|os\.getenv\([\'"]|os\.environ\[[\'"])([A-Z_][A-Z0-9_]*)', content)
                for env in env_matches:
                    if env not in ["NODE_ENV", "PRODUCTION"]:
                        self.metadata["env_vars"].add(env)

                if ext == '.py':
                    if "class " in content:
                        classes = re.findall(r'class\s+(\w+)', content)
                        for c in classes: self.metadata["modules"].append(c)
                    
                    if "def process" in content or "def handler" in content:
                        self.metadata["flow"].append(f"Logic --> {os.path.basename(filepath)}")

                    endpoints = re.findall(r'@(?:app|router)\.(get|post|put|delete)\([\'"](.+?)[\'"]\)', content)
                    for method, url in endpoints:
                        self.metadata["api_endpoints"].append(f"{method.upper()} {url}")
                    
                    imports = re.findall(r'^(?:from|import)\s+([\w-]+)', content, re.MULTILINE)
                    for imp in imports: self._add_dep('python', imp)

                elif ext in ['.js', '.ts', '.jsx']:
                    imports = re.findall(r'(?:import\s+.*\s+from|require)\s*[\'"]([@\w/-]+)[\'"]', content)
                    for imp in imports: 
                        if not imp.startswith('.'): self._add_dep('node', imp)
                    
                    if "mongoose.connect" in content: self.metadata["flow"].append("App --> Database")
        except: pass

    def _add_dep(self, lang, lib):
        if lang == 'python':
            if lib not in STD_LIBS['python']:
                self.metadata["dependencies"]["Python"].add(lib)
                if lib in ['flask', 'django', 'fastapi']: self.metadata["tech_stack"].add(f"Framework: {lib.capitalize()}")
                if lib in ['sqlalchemy', 'pymongo', 'psycopg2']: self.metadata["tech_stack"].add(f"Database: {lib.capitalize()}")
        elif lang == 'node':
            if lib not in STD_LIBS['node']:
                self.metadata["dependencies"]["Node.js"].add(lib)

    def generate_diagrams(self):
        # ... (Same as previous version, retained for brevity) ...
        diagrams = ""
        chart = "```mermaid\ngraph TD\n    User[User] --> UI[Client]\n"
        backend = self.metadata["entry_point"] or "Server"
        chart += f"    UI --> {backend}\n"
        
        for tech in self.metadata["tech_stack"]:
            clean_tech = tech.split(': ')[1]
            if "Database" in tech: chart += f"    {backend} --> {clean_tech}[({clean_tech})]\n"
            elif "Framework" in tech: chart += f"    {clean_tech} --> {backend}\n"
        
        if len(self.metadata["tech_stack"]) == 0 and self.metadata["modules"]:
             for mod in self.metadata["modules"][:4]: chart += f"    {backend} --> {mod}\n"
        chart += "```\n\n"
        
        flow = "```mermaid\nsequenceDiagram\n    participant User\n    participant System\n"
        has_db = any("Database" in t for t in self.metadata["tech_stack"])
        if has_db: flow += "    participant DB as Database\n"
        flow += "    User->>System: Request\n    System->>System: Process Logic\n"
        if has_db: flow += "    System->>DB: Query Data\n    DB-->>System: Return Data\n"
        flow += "    System-->>User: Response\n```"
        return "**System Architecture**\n" + chart + "**Data Flow**\n" + flow

    def build_markdown(self, template="Detailed"):
        m = self.metadata
        langs = sorted(list(m["languages"]))
        if not langs and m["dependencies"]["Python"]: langs.append("Python")
        if not langs and m["dependencies"]["Node.js"]: langs.append("Node.js")

        md = ""
        
        # --- NEW MINIMAL (FORMERLY DETAILED) ---
        if template == "Minimal":
            md += f"# {m['project_name']}\n\n"
            for l in langs: md += f"![{l}](https://img.shields.io/badge/Language-{l}-blue) "
            md += f"\n\n## 📝 Description\n{m['description']}\n\n"
            if self.custom_context: md += f"> **Context:** {self.custom_context}\n\n"
            
            md += "## 📑 Table of Contents\n- [Architecture](#-architecture)\n- [Installation](#-installation)\n- [Usage](#-usage)\n\n"
            
            md += "## 🏗 Architecture\n" + self.generate_diagrams() + "\n\n"
            md += "## ⚙️ Installation\n" + self._generate_strict_install(langs)
            md += "## 🚀 Usage\n" + self._generate_strict_usage(langs)
            
            if m["api_endpoints"]:
                md += "## 🔌 API Reference\n| Method | Endpoint |\n|---|---|\n"
                for ep in m["api_endpoints"][:5]:
                    parts = ep.split(' ')
                    md += f"| **{parts[0]}** | `{parts[1]}` |\n"
            
            md += f"\n## 📄 License\n**{m['license']}**"
            return md

        # --- NEW DETAILED (ENTERPRISE GRADE) ---
        
        # 1. Header with Advanced Badges
        md += f"# {m['project_name']}\n\n"
        user = m['username']
        repo = m['repo_name']
        
        # GitHub Live Badges
        if user != "username":
            md += f"[![GitHub Stars](https://img.shields.io/github/stars/{user}/{repo}?style=social)](https://github.com/{user}/{repo}/stargazers) "
            md += f"[![GitHub Forks](https://img.shields.io/github/forks/{user}/{repo}?style=social)](https://github.com/{user}/{repo}/network/members) "
            md += f"[![GitHub Issues](https://img.shields.io/github/issues/{user}/{repo})](https://github.com/{user}/{repo}/issues) "
            md += f"[![License](https://img.shields.io/github/license/{user}/{repo})](https://github.com/{user}/{repo}/blob/main/LICENSE)\n\n"
        else:
            # Fallback badges
            for l in langs: md += f"![{l}](https://img.shields.io/badge/Language-{l}-blue) "
            md += "\n\n"

        md += f"## 📝 Description\n{m['description']}\n\n"
        if self.custom_context: md += f"> **Developer Note:** {self.custom_context}\n\n"

        # 2. Expanded Table of Contents
        md += "## 📑 Table of Contents\n"
        md += "- [Features](#-features)\n- [Architecture](#-architecture)\n- [Tech Stack](#-tech-stack)\n- [Prerequisites](#-prerequisites)\n- [Environment Variables](#-environment-variables)\n- [Installation](#-installation)\n- [Running Tests](#-running-tests)\n- [Usage](#-usage)\n- [Deployment](#-deployment)\n- [Contributing](#-contributing)\n\n"

        # 3. Features (Placeholder)
        md += "## ✨ Features\n"
        md += "- [x] " + (f"RESTful API endpoints" if m["api_endpoints"] else "Core Logic Implementation") + "\n"
        md += "- [x] " + (f"Database Integration ({list(m['tech_stack'])[0].split(':')[1]})" if m['tech_stack'] else "Modular Architecture") + "\n"
        md += "- [ ] User Authentication (Planned)\n- [ ] CI/CD Pipeline\n\n"

        # 4. Architecture
        md += "## 🏗 Architecture\n" + self.generate_diagrams() + "\n\n"

        # 5. Tech Stack Table
        md += "## 🛠 Tech Stack\n| Category | Technology |\n|---|---|\n"
        md += f"| **Languages** | {', '.join(langs)} |\n"
        if m["tech_stack"]: md += f"| **Frameworks** | {', '.join([t.split(':')[1] for t in m['tech_stack'] if 'Framework' in t])} |\n"
        if any("Database" in t for t in m["tech_stack"]): md += f"| **Database** | {', '.join([t.split(':')[1] for t in m['tech_stack'] if 'Database' in t])} |\n"
        md += "\n"

        # 6. Environment Variables (NEW)
        if m["env_vars"]:
            md += "## 🔐 Environment Variables\n"
            md += "Create a `.env` file in the root directory:\n\n"
            md += "| Variable | Description |\n|---|---|\n"
            for env in m["env_vars"]:
                md += f"| `{env}` | Config value for {env.replace('_', ' ').title()} |\n"
            md += "\n"

        # 7. Installation
        md += "## ⚙️ Installation\n" + self._generate_strict_install(langs)

        # 8. Testing (NEW)
        if m["tests"]:
            md += "## 🧪 Running Tests\nTo execute the test suite:\n```bash\n"
            if "jest" in m["tests"]: md += "npm test\n"
            elif "pytest" in m["tests"]: md += "pytest\n"
            elif "go" in langs: md += "go test ./...\n"
            md += "```\n\n"

        # 9. Usage
        md += "## 🚀 Usage\n" + self._generate_strict_usage(langs)

        # 10. Deployment (NEW)
        if "DevOps: Docker" in m["tech_stack"]:
            md += "## 🐳 Deployment (Docker)\n"
            md += "```bash\n# Build image\ndocker build -t my-app .\n# Run container\ndocker run -p 3000:3000 my-app\n```\n\n"
        
        # 11. Contributing
        md += "## 🤝 Contributing\n1. Fork the Project\n2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)\n3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)\n4. Push to the Branch (`git push origin feature/AmazingFeature`)\n5. Open a Pull Request\n\n"
        
        md += f"## 📄 License\nDistributed under the **{m['license']}**."
        
        return md

    def _generate_strict_install(self, langs):
        steps = "1. **Clone the repository**\n   ```bash\n   git clone <repo_url>\n   ```\n"
        if "Python" in langs:
            steps += "2. **Python Setup**\n   ```bash\n   python -m venv venv\n   source venv/bin/activate\n"
            if self.metadata["dependencies"]["Python"]:
                 libs = " ".join(list(self.metadata["dependencies"]["Python"])[:8])
                 steps += f"   pip install {libs}\n"
            elif os.path.exists(os.path.join(self.path, 'requirements.txt')):
                 steps += "   pip install -r requirements.txt\n"
            steps += "   ```\n"
        if "Node.js" in langs: steps += "2. **Node.js Setup**\n   ```bash\n   npm install\n   ```\n"
        return steps

    def _generate_strict_usage(self, langs):
        cmd = ""
        if "Node.js" in langs:
            cmd += "**Node:**\n"
            if self.metadata["scripts"]:
                cmd += "| Command | Action |\n|---|---|\n"
                for k,v in self.metadata["scripts"].items():
                    if k in ['start', 'dev', 'test']: cmd += f"| `npm run {k}` | {v} |\n"
                cmd += "\n"
            else:
                entry = self.metadata["entry_point"] or "index.js"
                cmd += f"```bash\nnode {entry}\n```\n"
        if "Python" in langs:
            cmd += "**Python:**\n"
            entry = self.metadata["entry_point"] or "main.py"
            cmd += f"```bash\npython {entry}\n```\n"
        if not cmd: cmd += "```bash\n# Run main entry point\n```\n"
        return cmd

def generate_readme(path, template, context):
    scanner = DeepScanner(path, context)
    try:
        scanner.setup_path()
        scanner.scan()
        return scanner.build_markdown(template)
    finally:
        scanner.cleanup()